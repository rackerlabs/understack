# Ironic

See [Writing Ironic Drivers and Interfaces](../contributing/writing-ironic-drivers.md)
for how to add a new hardware type or interface. This page documents what
UnderStack ships today.

## Custom Hardware Types

UnderStack ships additional Ironic hardware types via the `ironic-understack`
Python package, registered as `ironic.hardware.types` entry points.

### netdev

The `netdev` hardware type is a stub type for network devices (firewalls,
load balancers) that Ironic tracks solely for Neutron physical port binding. It uses
noop or no-* interfaces for everything except `network`, which is set to
`neutron`. This means nodes of this type go through no deployment, inspection,
BIOS, RAID, rescue, or firmware lifecycle — Ironic only manages their port
bindings.

To use it, add `netdev` to `enabled_hardware_types` in `ironic.conf` and
ensure `noop` deploy and `neutron` network interfaces are also enabled.

### panos

The `panos` hardware type is a `netdev` for PAN-OS (Palo Alto) firewalls, so
these appliances can be told apart by their `driver`. It replaces the `netdev`
inspect and management interfaces with `panos` ones, which talk to the
appliance's XML API at `driver_info['management_ip']`. The no-op interfaces
remain available as fallbacks.

- **inspect** logs in and records the model and serial (only when enroll-fw
  hasn't already set them) and `firmware_version`. LLDP-based port
  discovery and HA peer discovery are not implemented yet.
- **management** has a `setup_initial_configuration` verify step, which
  currently only logs, and the manual clean steps `reset_to_factory_defaults`
  and `clear_configuration`. Those clean steps fail with "not implemented"
  instead of reporting success.

Credentials come from the `[netdev_panos]` oslo.config group. Login tries the
standard password first, then preconfig, then factory, so it works with
appliances at any point in their setup. `[netdev_panos] verify_ssl`
(default off) controls TLS verification.

To use it, add `panos` to `enabled_hardware_types`, `enabled_inspect_interfaces`,
and `enabled_management_interfaces`. Nodes enrolled before the `panos`
interfaces existed keep their stored `no-inspect` and `noop` interfaces until
they are switched with
`openstack baremetal node set --inspect-interface panos --management-interface panos`.
