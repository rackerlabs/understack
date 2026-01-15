#!/usr/bin/env bash

if [[ $1 == "--config" ]] ; then
  cat <<EOF
{
  "configVersion":"v1",
  "kubernetes":[{
    "apiVersion": "baremetal.ironicproject.org/v1alpha1",
    "kind": "IronicRunbook",
    "executeHookOnEvent":[ "Deleted" ]
  }]
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

    command_args=(baremetal runbook delete "${runbook_name}")
    echo "${kind}/${resource_name} deleted, running: openstack ${command_args[*]}"

    openstack "${command_args[@]}"
  fi
fi
