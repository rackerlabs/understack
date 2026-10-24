# understack-workflows

This Python package aims to provide all the scripts that we will
use inside of Argo Workflows.

## sync-keystone

This script takes an OpenStack Project ID and ensures the proper
operation happens against the Nautobot Tenants. Operations include
create, update and delete.


## enroll-server post-inspection runbooks

Optionally pass an ordered JSON array of runbook names or UUIDs:

```sh
enroll-server --ip-address 192.0.2.10 \
  --post-inspection-runbooks '["first-runbook", "second-runbook"]'
```

For Argo, use the `enroll-server` WorkflowTemplate parameter
`post_inspection_runbooks` with the same JSON array. It defaults to `[]`.

Runbooks execute sequentially after agent inspection and final BIOS
configuration, before RAID configuration, firmware updates, and `provide`.
Each requires at least one matching node/runbook trait (Ironic API 1.112 or
newer), uses the runbook's ramdisk setting, and waits for `manageable`.
A failed lookup, trait check, or cleaning operation stops enrollment.
