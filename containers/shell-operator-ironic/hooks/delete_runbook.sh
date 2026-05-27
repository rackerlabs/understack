#!/usr/bin/env bash

if [[ $1 == "--config" ]] ; then
  cat <<EOF
{
  "configVersion":"v1",
  "kubernetes":[{
    "apiVersion": "baremetal.ironicproject.org/v1alpha1",
    "kind": "IronicRunbook",
    "executeHookOnEvent":[ "Deleted" ]
  }],
  "settings": {
    "executionMinInterval": "30s",
    "executionBurst": 1
  }
}
EOF
else
  echo "[delete_runbook] Hook invoked, processing binding contexts"
  binding_count=$(jq -r 'length' "${BINDING_CONTEXT_PATH}")
  echo "[delete_runbook] Found ${binding_count} binding context(s)"

  for ((i = 0; i < binding_count; i++)); do
    type=$(jq -r ".[$i].type" "${BINDING_CONTEXT_PATH}")
    echo "[delete_runbook] Processing context=${i} type=${type}"

    if [[ $type == "Synchronization" ]] ; then
      echo "[delete_runbook] Synchronization event, nothing to do for deletes"
      continue
    fi

    if [[ $type == "Event" ]] ; then
      resource_name=$(jq -r ".[$i].object.metadata.name" "${BINDING_CONTEXT_PATH}")
      kind=$(jq -r ".[$i].object.kind" "${BINDING_CONTEXT_PATH}")
      runbook_name=$(jq -r ".[$i].object.spec.runbookName" "${BINDING_CONTEXT_PATH}")

      echo "[delete_runbook] Deleting runbook kind=${kind} name=${resource_name} runbookName=${runbook_name}"

      command_args=(baremetal runbook delete "${runbook_name}")
      echo "[delete_runbook] Running: openstack ${command_args[*]}"

      if output=$(openstack "${command_args[@]}" 2>&1); then
          echo "[delete_runbook] SUCCESS: Runbook deleted from Ironic name=${resource_name} output=${output}"
      else
          echo "[delete_runbook] FAILED: name=${resource_name} error=${output}" >&2
          exit 1
      fi
    fi
  done
  echo "[delete_runbook] Hook finished"
fi
