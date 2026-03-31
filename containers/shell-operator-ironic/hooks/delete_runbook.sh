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
    "executionMinInterval": 30s,
    "executionBurst": 1
  }
}
EOF
else
  binding_count=$(jq -r 'length' "${BINDING_CONTEXT_PATH}")
  for ((i = 0; i < binding_count; i++)); do
    type=$(jq -r ".[$i].type" "${BINDING_CONTEXT_PATH}")
    if [[ $type == "Synchronization" ]] ; then
      echo "Implement any reconciliation logic needed here."
      continue
    fi

    if [[ $type == "Event" ]] ; then
      resource_name=$(jq -r ".[$i].object.metadata.name" "${BINDING_CONTEXT_PATH}")
      kind=$(jq -r ".[$i].object.kind" "${BINDING_CONTEXT_PATH}")

      runbook_name=$(jq -r ".[$i].object.spec.runbookName" "${BINDING_CONTEXT_PATH}")

      command_args=(baremetal runbook delete "${runbook_name}")
      echo "${kind}/${resource_name} deleted, running: openstack ${command_args[*]}"

      openstack "${command_args[@]}"
    fi
  done
fi
