# understack-workflows

This Python package aims to provide all the scripts that we will
use inside of Argo Workflows.

## sync-keystone

This script takes an OpenStack Project ID and ensures the proper
operation happens against the Nautobot Tenants. Operations include
create, update and delete.


## Ironic runbooks

`apply-node-runbook` runs configured Ironic runbooks for a node, handling the
required state transitions. Runbooks execute in order; a failure stops the list.

```sh
apply-node-runbook --node NODE_UUID \
  --runbooks '["bmc-configure-snmpv3-user"]'
```

Only idle nodes in `available` or `manageable` are supported. Active nodes,
maintenance, conductor reservations, pending state transitions, and instance or
allocation associations are rejected before any state change. Errors include the
node state and blocking field value. An idle node with an instance UUID must have
its association investigated and resolved separately; the runner never clears it.

For `available` nodes, the runner transitions to `manageable`, runs manual
cleaning, then requests `provide` to return to `available`. Nodes starting in
`manageable` remain there. Failures stop the sequence without restoring the
starting state; inspect the Ironic error before retrying.

For automatic execution after enrollment, configure `post_enroll_workflows`
with WorkflowTemplates that accept `node_uuid`.
