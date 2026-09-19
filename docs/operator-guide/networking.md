# Network Operations

This section is for network operations and system operators working with
UnderStack's control plane or tenant data plane:

- [Neutron](openstack-neutron.md) — configure router flavors, service profiles,
  and VNI allocation.
- [OVN / Open vSwitch](ovs-ovn.md) — diagnose agents, chassis, logical routers,
  and traffic flow.
- [kubectl-us](kubectl-us.md) — inspect OpenStack and OVN objects through
  a single troubleshooting CLI.
- [Neutron Networking Design](../design-guide/neutron-networking.md) — understand
  the tenant networking and fabric model behind the operational procedures.
- [Control Plane Network Requirements](../deploy-guide/control-plane-network-requirements.md)
  — what the control plane nodes need on the wire: an OVS bridge with trunk
  access to the provider VLAN range, and the switch-side configuration it implies.

For failures that may not be network-specific, start from the broader
[Troubleshooting index](troubleshooting.md).
