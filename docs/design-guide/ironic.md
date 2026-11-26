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

To use it, add `panos` to `enabled_hardware_types`, `enabled_firmware_interfaces`,
`enabled_inspect_interfaces`, and `enabled_management_interfaces`. Nodes
enrolled before the `panos` interfaces existed keep their stored `no-firmware`,
`no-inspect` and `noop` interfaces until they are switched with
`openstack baremetal node set --firmware-interface panos --inspect-interface panos --management-interface panos`.

The firmware interface does not flash anything. Its `cache_firmware_components`
step (a verify, manual clean, and service step) records the PAN-OS release and
the installed content versions (applications, antivirus, WildFire, GlobalProtect
client, device dictionary) as the node's firmware components.

### cisco_nxos

The `cisco_nxos` hardware type is a `netdev` for Cisco NX-OS (Nexus) switches.
It replaces the `netdev` inspect and firmware interfaces with `cisco_nxos`
ones, which talk to NX-API (JSON-RPC over HTTPS) at
`driver_info['nxos_address']`. The switch needs `feature nxapi`. Both
interfaces only run `show` commands and never change the switch
configuration. The no-op interfaces remain available as fallbacks.

- **inspect** records the NX-OS release as a firmware component and
  creates a baremetal port named `<node>:<interface>` (e.g.
  `f20-3-1:Ethernet1/5`) for each physical Ethernet interface, with the
  interface's burned-in MAC as its address and PXE disabled. It also records
  the switch MAC from `show vdc detail` as `properties['chassis_mac']`, so a
  server's LLDP data from its BMC can be matched whichever chassis ID the
  switch sends: by default NX-OS sends each interface's own MAC (matching a
  port's address), and with `lldp chassis-id switch` it sends the switch MAC
  (matching `chassis_mac`). The LLDP port ID matches the interface in the port
  name either way. A switch that can't report its MAC or LLDP setting is
  logged, not failed.
- **inspection data** is stored like any other inspect interface's, so
  `openstack baremetal node inventory save` returns it. The inventory has
  the standard `interfaces` (name and MAC) and `system_vendor`, shaped like
  redfish inspection's: `manufacturer`, `product_name` (the chassis model) and
  `serial_number` from `show version`, each left out if not reported. Inspect
  doesn't write the model or serial to the node itself; inspection rules can
  copy them from here (for example to `extra.serial`). The plugin data has `nxos_version`, `chassis_mac` and
  `lldp_chassis_id`, read from `show running-config lldp`: `switch` when
  `lldp chassis-id switch` is configured, `interface` otherwise, or null if it
  couldn't be read.
- **ports:** on re-inspection an existing port with that name has its MAC
  corrected. A port that already has the MAC under another name is left
  alone. A port that can't be created or corrected because its MAC or name is
  already used by another port (for example two interfaces whose MACs
  swapped) is logged and skipped for an operator to sort out. Ports for
  interfaces the switch no longer reports are logged but never deleted.
  The structured commands go to the switch in one NX-API request.
- **firmware** does not flash anything. Its `cache_firmware_components` step
  (a verify, manual clean, and service step) records the running NX-OS release
  as the `nxos` firmware component.

Credentials are read from `driver_info`, named like the redfish driver's:
`nxos_username`, `nxos_password`, and `nxos_verify_ca` (a Boolean or a path to
a CA bundle). Any of them left unset falls back to the same option in the
`[cisco_nxos]` oslo.config group (`username`, `password`, `verify_ca`), so a
shared account can be configured once for the conductor and overridden per
node. A node must end up with a username and password from one or the other.
`verify_ca` defaults to false because switches ship with self-signed
certificates. Ironic masks `nxos_password` in API responses like any other
`*password*` key.

To use it, add `cisco_nxos` to `enabled_hardware_types`,
`enabled_firmware_interfaces`, and `enabled_inspect_interfaces`.
