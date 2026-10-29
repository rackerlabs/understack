# understack-workflows

This Python package aims to provide all the scripts that we will
use inside of Argo Workflows.

## sync-keystone

This script takes an OpenStack Project ID and ensures the proper
operation happens against the Nautobot Tenants. Operations include
create, update and delete.

## enroll-server

Enrolls servers in Ironic. Optional runbooks run in order after inspection and
BIOS configuration, before RAID configuration, firmware updates, and making
the node available. A runbook failure stops enrollment.

Pass runbook names or UUIDs as a JSON array:

```sh
enroll-server --ip-address 192.0.2.10 \
  --post-inspection-runbooks '["first-runbook", "second-runbook"]'
```

For Argo, pass the same JSON array with `-p post_inspection_runbooks='["runbook"]'`.
Use `-p post_inspection_runbooks='[]'` to skip runbooks.
