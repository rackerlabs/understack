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
    "executionMinInterval": 30s,
    "executionBurst": 1
  }
}
EOF
else
  type=$(jq -r '.[0].type' "${BINDING_CONTEXT_PATH}")
  if [[ $type == "Synchronization" ]] ; then
    echo "Implement any reconciliation logic needed here."
  fi

  if [[ $type == "Event" ]] ; then
    resource_name=$(jq -r '.[0].object.metadata.name' "${BINDING_CONTEXT_PATH}")
    kind=$(jq -r '.[0].object.kind' "${BINDING_CONTEXT_PATH}")

    runbook_name=$(jq -r '.[0].object.spec.runbookName' "${BINDING_CONTEXT_PATH}")
    public=$(jq -r '.[0].object.spec.public' "${BINDING_CONTEXT_PATH}")
    owner=$(jq -r '.[0].object.spec.owner' "${BINDING_CONTEXT_PATH}")
    jq -r '.[0].object.spec.steps' "${BINDING_CONTEXT_PATH}" > /tmp/steps.yaml

    # Ironic's runbook extra field is essentially a dict of dicts, representing a key values. baremetal cli allows you
    # to pass in multiple --extra options, adding any you do pass. We would need to make an initial query to determine
    # existing extras, and then sync the differences. This work is probably better suited to a full controller implementation.
    # extra=$(jq -r '.spec.extra | [to_entries[] | "--extra \(.key)=\(.value | @json | @sh)"] | join(" ")' ${BINDING_CONTEXT_PATH})

    command_args=(baremetal runbook create --name "${runbook_name}" --public "${public}" --steps /tmp/steps.yaml)
    if [[ -n "${owner}" && "${owner}" != "null" ]]; then
        command_args+=(--owner "${owner}")
    fi

    echo "${kind}/${resource_name} created, running: openstack ${command_args[*]}"

    openstack "${command_args[@]}"
  fi
fi
