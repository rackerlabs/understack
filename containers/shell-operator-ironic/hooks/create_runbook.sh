#!/usr/bin/env bash

if [[ $1 == "--config" ]] ; then
  cat <<EOF
{
  "configVersion":"v1",
  "kubernetes":[{
    "apiVersion": "baremetal.ironicproject.org/v1alpha1",
    "kind": "IronicRunbook",
    "executeHookOnEvent":[ "Added" ]
  }],
  "settings": {
    "executionMinInterval": "30s",
    "executionBurst": 1
  }
}
EOF
else
  patch_status() {
    local namespace="$1"
    local name="$2"
    local sync_status="$3"
    local message="${4:-}"
    local now
    now=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    local condition_status="True"
    local reason="SyncSucceeded"
    if [[ "${sync_status}" == "Failed" ]]; then
        condition_status="False"
        reason="SyncFailed"
    fi

    local patch
    patch=$(cat <<PATCH
{
  "status": {
    "syncStatus": "${sync_status}",
    "lastSyncTime": "${now}",
    "conditions": [
      {
        "type": "Ready",
        "status": "${condition_status}",
        "lastTransitionTime": "${now}",
        "reason": "${reason}",
        "message": "${message}"
      }
    ]
  }
}
PATCH
)
    echo "[create_runbook] Patching status namespace=${namespace} name=${name} syncStatus=${sync_status}"
    kubectl patch ironicrunbook "${name}" -n "${namespace}" \
        --type merge --subresource status -p "${patch}" 2>/dev/null || \
    echo "[create_runbook] WARNING: failed to patch status for ${name}"
  }

  sync_runbook() {
    local i="$1"
    local resource_name namespace kind runbook_name description public owner

    resource_name=$(jq -r ".${i}.metadata.name" "${BINDING_CONTEXT_PATH}")
    namespace=$(jq -r ".${i}.metadata.namespace" "${BINDING_CONTEXT_PATH}")
    kind=$(jq -r ".${i}.kind" "${BINDING_CONTEXT_PATH}")
    runbook_name=$(jq -r ".${i}.spec.runbookName" "${BINDING_CONTEXT_PATH}")
    description=$(jq -r ".${i}.spec.description // empty" "${BINDING_CONTEXT_PATH}")
    public=$(jq -r ".${i}.spec.public // empty" "${BINDING_CONTEXT_PATH}")
    owner=$(jq -r ".${i}.spec.owner // empty" "${BINDING_CONTEXT_PATH}")

    echo "[create_runbook] Creating runbook kind=${kind} name=${resource_name} namespace=${namespace} runbookName=${runbook_name} description=${description} public=${public} owner=${owner}"

    jq -r ".${i}.spec.steps" "${BINDING_CONTEXT_PATH}" > /tmp/steps.json

    command_args=(baremetal runbook create --name "${runbook_name}" --steps /tmp/steps.json)

    if [[ -n "${description}" ]]; then
        command_args+=(--description "${description}")
    fi
    if [[ -n "${public}" ]]; then
        command_args+=(--public "${public}")
    fi
    if [[ -n "${owner}" ]]; then
        command_args+=(--owner "${owner}")
    fi

    echo "[create_runbook] Running: openstack ${command_args[*]}"

    if output=$(openstack "${command_args[@]}" 2>&1); then
        echo "[create_runbook] SUCCESS: Runbook created in Ironic name=${resource_name} output=${output}"

        traits_json=$(jq -c ".${i}.spec.traits // []" "${BINDING_CONTEXT_PATH}")
        if [[ "${traits_json}" != "[]" ]]; then
            echo "[create_runbook] Setting traits name=${resource_name} traits=${traits_json}"
            ironic_endpoint=$(openstack endpoint list --service baremetal --interface internal -f value -c URL 2>/dev/null | head -1)
            if [[ -n "${ironic_endpoint}" ]]; then
                token=$(openstack token issue -f value -c id)
                echo "[create_runbook] PUT ${ironic_endpoint}/v1/runbooks/${runbook_name}/traits"
                trait_response=$(curl -s -X PUT \
                    -H "Content-Type: application/json" \
                    -H "X-Auth-Token: ${token}" \
                    -H "X-OpenStack-Ironic-API-Version: 1.112" \
                    -d "{\"traits\": ${traits_json}}" \
                    "${ironic_endpoint}/v1/runbooks/${runbook_name}/traits")
                echo "[create_runbook] Traits response name=${resource_name} response=${trait_response}"
            else
                echo "[create_runbook] WARNING: Could not determine Ironic endpoint for traits"
            fi
        else
            echo "[create_runbook] No traits to set name=${resource_name}"
        fi

        patch_status "${namespace}" "${resource_name}" "Synced" "Successfully created runbook in Ironic"
        echo "[create_runbook] Completed name=${resource_name} status=Synced"
    else
        # If it already exists, that's OK during sync - not an error
        if echo "${output}" | grep -qi "already exists\|Conflict\|409"; then
            echo "[create_runbook] Runbook already exists in Ironic name=${resource_name}, skipping create"
            patch_status "${namespace}" "${resource_name}" "Synced" "Runbook already exists in Ironic"
        else
            echo "[create_runbook] FAILED: name=${resource_name} error=${output}" >&2
            patch_status "${namespace}" "${resource_name}" "Failed" "${output}"
            return 1
        fi
    fi
  }

  echo "[create_runbook] Hook invoked, processing binding contexts"
  binding_count=$(jq -r 'length' "${BINDING_CONTEXT_PATH}")
  echo "[create_runbook] Found ${binding_count} binding context(s)"

  for ((i = 0; i < binding_count; i++)); do
    type=$(jq -r ".[$i].type" "${BINDING_CONTEXT_PATH}")
    echo "[create_runbook] Processing context=${i} type=${type}"

    if [[ $type == "Synchronization" ]] ; then
      echo "[create_runbook] Synchronization event, reconciling existing resources"
      objects_count=$(jq -r ".[$i].objects | length" "${BINDING_CONTEXT_PATH}")
      echo "[create_runbook] Found ${objects_count} existing IronicRunbook(s) to reconcile"
      for ((j = 0; j < objects_count; j++)); do
        obj_name=$(jq -r ".[$i].objects[$j].object.metadata.name" "${BINDING_CONTEXT_PATH}")
        obj_sync=$(jq -r ".[$i].objects[$j].object.status.syncStatus // empty" "${BINDING_CONTEXT_PATH}")
        echo "[create_runbook] Checking name=${obj_name} syncStatus=${obj_sync}"
        if [[ -z "${obj_sync}" || "${obj_sync}" == "null" ]]; then
          echo "[create_runbook] Resource name=${obj_name} has no syncStatus, needs reconciliation"
          # Re-map the jq path to point at the object within the sync event
          ORIG_BINDING_CONTEXT_PATH="${BINDING_CONTEXT_PATH}"
          jq -r ".[$i].objects[$j].object" "${BINDING_CONTEXT_PATH}" > /tmp/sync_object.json
          BINDING_CONTEXT_PATH=/tmp/sync_object.json
          sync_runbook ""
          BINDING_CONTEXT_PATH="${ORIG_BINDING_CONTEXT_PATH}"
        else
          echo "[create_runbook] Resource name=${obj_name} already synced, skipping"
        fi
      done
      continue
    fi

    if [[ $type == "Event" ]] ; then
      sync_runbook "[$i].object"
      if [[ $? -ne 0 ]]; then
        exit 1
      fi
    fi
  done
  echo "[create_runbook] Hook finished"
fi
