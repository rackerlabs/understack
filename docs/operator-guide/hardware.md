# Hardware Operations

This section is for data centre technicians and operators working with an
individual physical machine. Start with the task you need to perform:

- [Device Type Management](device-types.md) — define and validate the hardware
  models supported by a deployment.
- [Flavor Management](flavors.md) — map resource classes and hardware traits to
  Nova flavors.
- [Ironic](openstack-ironic.md) — inspect or manually create bare metal nodes
  and ports.
- [Ironic Inspection Guide](openstack-ironic-inspection-guide.md) — diagnose
  hardware inspection failures.
- [Change Boot Interface](openstack-ironic-change-boot-interface.md) — change
  how a node boots for provisioning.
- [Baremetal Box Cleanup Runbook](baremetal-ironic-cleanup-runbook.md) — recover
  a node stuck in a failed provisioning state.
- [Ironic Console](openstack-ironic-console.md) — access a node's serial
  console.
- [Server Firmware Updates](server-firmware-update.md) — update firmware from
  the operator side.
- [BMC Password](bmc-password.md) — retrieve the generated password for a
  server's management controller.

Schema definitions for device types, traits, and flavors live under
[Reference](../reference/index.md#hardware-definitions).
