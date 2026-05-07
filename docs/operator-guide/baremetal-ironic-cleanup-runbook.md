# Baremetal Box Cleanup Runbook

This runbook is for operators returning an Ironic baremetal node to the reusable
pool.

The larger operational problem is that some machines can drift out of sync
between Ironic, Nautobot, Neutron, and the switch configuration. When that
happens, we need a safe process to inspect the machine again, verify the
data, and then clean or return it to service.

Operator rule of thumb: start with node state, tenant ownership, the last error,
and the next safe command. The repository/config details are kept later as
evidence so the process stays auditable without making the first page feel like
a config review.

This document is only for Ironic baremetal box cleanup.

## What This Runbook Covers

- when cleanup is automated and when a human should intervene
- how to decide whether a node is safe to inspect or clean
- how to handle stale/out-of-sync data before retrying cleanup
- which Ironic states require manual investigation
- where existing Ironic runbooks fit today
- what is not currently automated or configured

## Manual vs Automated

We do not manually run every cleanup command during normal operation.

Normal paths:

- Enrollment workflow runs the enrollment steps and finishes by moving the node
  to `provide`.
- Tenant delete should recycle the baremetal node without an operator command.
- The reclean workflow can run `manage`, check state, and run `provide` for a
  node that reaches `clean failed`.

Manual operator steps are needed when:

- the node is stuck in `clean failed`
- the reclean workflow did not run or did not fix the node
- the node is in maintenance and needs a human decision
- the last error points to a real issue, such as BMC reachability, disk/RAID
  failure, stale cleanup state, or provisioning network failure

## Manual Operator Steps

Use these steps when a human is handling a failed cleanup.

1. Confirm the node is safe to touch.

```bash
openstack baremetal node show <node> \
  -f yaml \
  -c uuid \
  -c name \
  -c provision_state \
  -c instance_uuid \
  -c maintenance \
  -c maintenance_reason \
  -c target_provision_state \
  -c last_error
```

If `instance_uuid` is set, stop and confirm whether the node is still attached
to a Nova server or failed tenant deployment.

1. Read the failure.

```bash
openstack baremetal node show <node> -f value -c last_error
openstack baremetal node show <node> -f yaml -c driver_internal_info
```

If node history is available:

```bash
openstack baremetal node history list <node>
openstack baremetal node history get <node> <event-uuid>
```

For nodes in `clean wait`, pay special attention to:

- `agent_last_heartbeat`
- `agent_url`
- `clean_steps`
- `dnsmasq_tag`
- `post_bios_reboot_requested`
- any `cleaning_vif_port_id` on the PXE-enabled Ironic port

1. Check the Ironic ports.

```bash
openstack baremetal port list --node <node> --long
```

Record `pxe_enabled`, `physical_network`, `local_link_connection`, and
`extra.bios_name`.

If the PXE-enabled Ironic port has `internal_info.cleaning_vif_port_id`, verify
that the matching Neutron port still exists:

```bash
openstack port show <cleaning_vif_port_id>
```

If Neutron returns `No Port found`, the node may be stuck in stale cleanup
state. Check Ironic conductor logs before unsetting maintenance or retrying
`manage` / `provide`.

1. Fix the cause reported by the error/logs.

This is the judgment step. Do not retry cleanup until the cause has been
understood. The reclean workflow retries the state transition, but it does not
repair ports, cabling, switch config, BMC reachability, disk errors, RAID
errors, or maintenance state.

1. If maintenance is set, clear it only after validation.

```bash
openstack baremetal node maintenance unset <node>
```

1. Move the node to `manageable`.

```bash
openstack baremetal node manage --wait 0 <node>
```

1. Trigger the configured cleanup path.

```bash
openstack baremetal node provide --wait 0 <node>
```

1. Watch until the node reaches a final state.

```bash
watch openstack baremetal node show <node> -f value -c provision_state
```

Expected successful end state: `available`.

## State Guide For Cleanup

| Node state | Operator action |
| --- | --- |
| `available` with no `instance_uuid` | Already reusable. Do not reclean unless there is a specific reason. |
| `manageable` with no `instance_uuid` | Safe operator state. Running `provide` starts the configured cleanup path. |
| `cleaning` | Cleanup is running. Watch progress before intervening. |
| `clean wait` | Cleanup is waiting on the agent or a clean step. Check `last_error`, `driver_internal_info`, IPA heartbeat, the cleaning VIF, and maintenance before retrying. |
| `clean failed` | Manual intervention state. Read the error, inspect ports/logs, fix the cause, then retry `manage` -> `provide`. |
| `active` with `instance_uuid` set | Tenant-owned. Do not clean directly; use the normal Nova delete/recycle path or investigate the tenant workflow. |
| `active` with no `instance_uuid` | Not normal for the reusable pool. Confirm owner/lessee and node history before changing state. |
| `deploy failed` with `instance_uuid` set | Treat as a failed tenant deployment first. Do not clean until Nova/Ironic ownership is understood. |
| `deploy failed` with no `instance_uuid` | Manual investigation state. Read `last_error` and history before deciding whether to move through cleanup. |
| `inspect failed` | Fix inspection first; cleanup depends on correct port and boot data. |
| `inspecting` or `inspect wait` | Inspection is in progress or waiting. Do not start cleanup until inspection finishes or fails. |
| `deleting` | A tenant delete/recycle path is in progress. Monitor; do not manually reclean unless it fails or stalls. |
| `error`, `rescue failed`, `unrescue failed`, or `service failed` | Quarantine-style failure states. Investigate the specific failure path before using the cleanup runbook. |
| Any state with `maintenance=True` | Human stop point. Read `maintenance_reason` and validate the node before unsetting maintenance or retrying cleanup. |

## Worked Example: Clean Wait With Missing Cleaning VIF

This pattern was seen on `Dell-C3GSW04`.

Node state:

```yaml
provision_state: clean wait
target_provision_state: available
maintenance: true
maintenance_reason: null
last_error: null
driver_internal_info:
  agent_last_heartbeat: '<old timestamp>'
  agent_url: https://<ipa-address>:9999
  clean_steps: null
  dnsmasq_tag: <uuid>
  post_bios_reboot_requested: true
```

The PXE-enabled Ironic port had:

```yaml
pxe_enabled: true
physical_network: f20-3-network
local_link_connection:
  switch_info: f20-3-1.iad3.rackspace.net
internal_info:
  cleaning_vif_port_id: <neutron-port-uuid>
```

Then the Neutron port lookup failed:

```bash
openstack port show <neutron-port-uuid>
```

```text
No Port found for <neutron-port-uuid>
```

How to read this:

- This is not an example of the historical wrong-secondary-switch PXE issue.
  That older issue came from stale/old inspection behavior and is not expected
  as a normal cleanup failure pattern.
- In this example, the PXE-enabled port points at the expected primary `-1`
  switch.
- Ironic still has a cleaning VIF recorded, but Neutron no longer has that
  port.
- The stale IPA heartbeat plus missing Neutron port suggests an interrupted or
  stale cleanup session.

Operator action:

- Do not immediately unset maintenance or retry `provide`.
- Check Ironic conductor logs for the node UUID around the last heartbeat and
  the transition into `clean wait`.
- Decide the recovery path after confirming why the cleaning VIF disappeared.

## Worked Example: Deploy Failed With Tenant Instance

This pattern was seen on `Dell-93GSW04`.

Node state:

```yaml
provision_state: deploy failed
target_provision_state: active
maintenance: false
last_error: null
instance_uuid: <nova-server-uuid>
instance_info:
  display_name: <server-name>
  project_id: <project-uuid>
  project_name: <project-name>
  fixed_ips: <tenant-fixed-ips>
```

The latest node history showed:

```text
Deploy step deploy.switch_to_tenant_network failed
Error changing node to tenant networks after deploy.
Could not add public network VIF <vif-uuid> to node <node-uuid>.
Deployment aborted at step 'switch_to_tenant_network'.
```

How to read this:

- This is not a normal box cleanup case.
- The node still has `instance_uuid`, so treat it as a failed tenant deployment.
- The failure happened after image deploy, during the tenant network handoff.
- Do not run `provide` or reclean until the Nova server ownership/state is
  understood.

Operator action:

```bash
openstack server show <instance_uuid>
```

If the server is not visible in the current cloud/project context, search by
server UUID or name with an admin/all-projects view before changing the Ironic
node state.

## Worked Example: Active With No Instance UUID

This pattern was seen on `1327172-hp1`.

Node state:

```yaml
provision_state: active
target_provision_state: null
instance_uuid: null
owner: <project-uuid>
lessee: null
maintenance: true
maintenance_reason: null
last_error: null
```

How to read this:

- `active` means Ironic does not consider the node available for scheduling.
- `instance_uuid: null` means it is not clearly attached to a Nova server.
- `maintenance: true` means a human must decide why the node is held out of
  service.

Operator action:

- Do not treat this as a normal cleanup candidate.
- Check node history before changing state.
- Confirm with the owning team/project whether the node is intentionally held,
  platform-owned, stale, or part of another workflow.
- Do not run `manage`, `provide`, or cleanup until ownership and purpose are
  understood.

## Worked Example: Inspect Failed With Neutron Port Not Active

This pattern was seen on `Dell-G3GSW04` and `Dell-73GSW04` after re-running
inspection.

Node state:

```yaml
provision_state: inspect failed
last_error: null
```

Node history showed:

```text
Failed to inspect hardware. Reason: unable to start inspection:
Port <neutron-port-uuid> failed to reach status ACTIVE
```

How to read this:

- `last_error` can be empty even when node history has the useful failure.
- Inspection did not get far enough to refresh hardware data.
- The failure is in the provisioning network path for the inspection boot.
- Do not continue to cleanup until inspection is fixed and the node returns to
  `manageable`.

Operator action:

```bash
openstack port show <neutron-port-uuid>
openstack baremetal port list --node <node> --long
```

Check Neutron/Undersync and the Ironic port data before retrying inspection.

## Normal Cleanup Entry Points

### Enrollment

The enrollment flow is implemented in
`enroll_server.py`.

Operator-level flow:

```mermaid
flowchart TD
    A[BMC discovery]
    B[Ironic node create/update]
    C[out-of-band inspection]
    D[agent inspection]
    E[BIOS/PXE setup]
    F[optional RAID]
    G[optional firmware update runbooks]
    H[provide]
    I[available]

    A --> B --> C --> D --> E --> F --> G --> H --> I

The final state transition in code is:

```python
ironic_node.transition(node, target_state="provide", expected_state="available")
```

### Tenant Delete

When a tenant server delete succeeds normally, no operator command is expected.
If the node lands in `clean failed`, use the manual operator steps above.

### Reclean Automation

The reclean workflow is defined in
`reclean-server.yaml`.

It runs:

```text
openstack baremetal node manage --wait 0 <device_uuid>
openstack baremetal node show -f value -c provision_state <device_uuid>
openstack baremetal node provide --wait 0 <device_uuid>
```

The `provide` step only runs when the node state returned by the middle step is
`manageable`.

The workflow does not clear maintenance. If `maintenance: true` is set on the
node, treat that as a human stop point. Maintenance is not cleared by this
workflow, so an operator should decide whether it is safe to unset maintenance
before retrying. Use the manual operator steps above if the node is in
maintenance.

## Runbooks Operators May Encounter

Firmware update cleanup is already modeled with Ironic runbooks.

The workflow is defined in
`server-firmware-update.yaml`.

It finds node traits matching `CUSTOM_FIRMWARE_UPDATE_`, looks up the matching
Ironic runbook, and runs:

```text
openstack baremetal node clean --runbook <runbook_uuid> --wait 0 <node_id>
```

The guide for this is
[server-firmware-update.md](server-firmware-update.md).

There is also an existing manual-clean example in
[openstack-ironic-change-boot-interface.md](openstack-ironic-change-boot-interface.md):

```text
openstack baremetal node clean --clean-steps dell-boot-config.yaml <NODE>
```

That document is for Dell boot-interface configuration. It is not the default
box cleanup path.

## Repo Evidence

We do not need this section for every cleanup, but it explains why the
commands above are the current supported process.

### Cleaning Configuration

The current Ironic cleaning configuration is in
`values.yaml`:

```yaml
conf:
  ironic:
    deploy:
      erase_devices_priority: 0
      erase_devices_metadata_priority: 0

    conductor:
      automated_clean: true
      clean_step_priority_override: deploy.erase_devices_express:95

    dhcp:
      dhcp_provider: dnsmasq

    inspector:
      add_ports: "all"
      extra_kernel_params: ipa-collect-lldp=1
      hooks: "ramdisk-error,validate-interfaces,architecture,pci-devices,parse-lldp,update-baremetal-port"
      keep_ports: "present"

    redfish:
      inspection_hooks: "validate-interfaces,ports,port-bios-name,architecture,pci-devices,resource-class"
```

Current meaning:

- Ironic automated cleaning is enabled with `automated_clean: true`.
- The older default disk erase priorities are set to `0`.
- `deploy.erase_devices_express` is enabled through
  `clean_step_priority_override: deploy.erase_devices_express:95`.
- The default box cleanup path is not configured as an Ironic runbook in this
  repository. It is Ironic automated cleaning with a clean-step priority
  override.

### Reclean Sensor And Alert

The clean-failed alert is defined in
`pr-clean-failed-servers.yaml`:

```promql
openstack_ironic_node{provision_state="clean failed"} == 1
```

The reclean sensor is defined in
`sensor-ironic-node-reclean.yaml`.

The sensor filters for:

```yaml
event_type: baremetal.node.power_set.end
payload.ironic_object.data.provision_state: clean failed
```

The sensor and `reclean-server.yaml` both use `device_uuid`.

There is also a checked-in clean-failed sample event at
`ironic_versioned_notifications_clean_failed.json`.
That sample uses:

```json
"event_type": "baremetal.node.power_set.start"
```

The sensor filters for `power_set.end`, not `power_set.start`. The checked-in
sample alone does not prove that the reclean sensor fires; use Argo sensor logs
or event-source logs when verifying this behavior in an environment.

### Runbook CRD

The runbook CRD is defined under
`runbook-crd`, and the shell operator hook
that syncs Kubernetes `IronicRunbook` objects into Ironic is
`create_runbook.sh`.

Checked-in sample runbooks include:

| File | Runbook name |
| --- | --- |
| `runbook_disk_cleaning.yaml` | `CUSTOM_DISK_CLEAN` |
| `runbook_raid_config.yaml` | `CUSTOM_STORAGE_RAID` |
| `runbook_firmware_update.yaml` | `CUSTOM_FIRMWARE_UPDATE` |

These are sample manifests in the repository. This document does not assume
they are deployed unless the environment confirms that.

## Key Files

| File | Why it matters |
| --- | --- |
| `values.yaml` | Current Ironic cleaning, inspector, DHCP, and Redfish hook configuration |
| `enroll_server.py` | Enrollment order and final `provide` transition |
| `ironic_node.py` | Helper functions for Ironic state transitions, RAID clean steps, and firmware runbooks |
| `reclean-server.yaml` | Existing Argo reclean workflow |
| `sensor-ironic-node-reclean.yaml` | Existing clean-failed event sensor |
| `pr-clean-failed-servers.yaml` | Existing clean-failed Prometheus alert |
| `server-firmware-update.yaml` | Existing firmware runbook workflow |
| `runbook-crd/samples` | Sample runbook manifests, not assumed deployed |
