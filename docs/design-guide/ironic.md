# Ironic

## Custom Hardware Types

UnderStack ships additional Ironic hardware types via the `ironic-understack`
Python package, registered as `ironic.hardware.types` entry points.

### netdev

The `netdev` hardware type is a stub type for network devices (switches,
routers) that Ironic tracks solely for Neutron physical port binding. It uses
noop or no-* interfaces for everything except `network`, which is set to
`neutron`. This means nodes of this type go through no deployment, inspection,
BIOS, RAID, rescue, or firmware lifecycle — Ironic only manages their port
bindings.

To use it, add `netdev` to `enabled_hardware_types` in `ironic.conf` and
ensure `noop` deploy and `neutron` network interfaces are also enabled.
