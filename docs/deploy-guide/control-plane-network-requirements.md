# Control Plane Network Requirements

What UnderStack needs from the networking on the nodes running the control
plane. How you build it is out of scope — these are the requirements the
deployment assumes.

This is the **provider network** path that OVN uses for tenant and external
traffic. For the provisioning network — MetalLB for DHCP and the dnsmasq
ranges — see [Networking](../networking.md).

## Summary

| Requirement | Detail |
| --- | --- |
| OVS bridge | An OVS bridge per node, named in `ovn_bridge_mappings` (conventionally `br-ex`). |
| Trunk uplink | That bridge reaches the physical network over a **trunk** carrying the whole provider VLAN range. |
| Independent host path | Host networking — IP, default route, DNS — must **not** depend on that bridge. |
| Non-overlapping VLANs | The provider VLAN range must not include any VLAN the host itself uses. |
| MTU | The trunk must carry the provider MTU plus the 4-byte VLAN tag. |

## Trunk access

OVN does not use a fixed VLAN. Neutron allocates a segmentation ID per provider
network from the VLAN [network segment
range](../design-guide/neutron-networking.md#vlans) configured for the fabric,
and `ovn-controller` adds a localnet port carrying that tag to the bridge named
in `ovn_bridge_mappings`.

Consequences for the uplink:

- It is a **trunk**, not an access port. Tags appear and disappear as networks
  are created and deleted.
- The switch port must permit the full provider VLAN range up front. A tag
  allocated after the node was configured must work with no host-side change.
- Nothing may strip or rewrite tags between the bridge and the switch.

The bridge also carries **arbitrary MACs** — tenant instance MACs and OVN
router gateway MACs, not just the host's. Any filtering on source MAC, or any
delivery mechanism that only delivers frames matching a known MAC, will drop
provider traffic.

## Host networking must be independent of the bridge

The straightforward build is to enslave the host's bond to the OVS bridge and
put the host IP on the bridge's internal port. It works, and it puts the OVS
datapath in front of everything the node does — SSH, kubelet, etcd, VRRP,
Geneve, and Ironic PXE/DHCP. An OVS or OVN fault then removes the node from the
network entirely, turning a dataplane problem into a lost node.

Give the bridge an uplink of its own instead. A kernel netdev cannot be both an
OVS bridge port and the host L3 interface, so the two cannot share one
interface.

Where that uplink comes from is yours to decide. A dedicated port pair is the
simplest and gives real bandwidth isolation. Where the nodes have only two
ports cabled, SR-IOV can carve the uplink out of them — host on the physical
function bond, bridge on a virtual function — at the cost of several
constraints on bonding mode and VF configuration, since a VF cannot run LACP
and needs explicit settings to carry a trunk at all.

An addressless bridge on every control plane node also makes gateway chassis
placement a scheduling decision rather than a host networking one.

## VLAN space

If the host and the bridge share one trunk, they share one VLAN space. The
provider segment range must exclude:

- the management VLAN carrying the host's untagged traffic
- every tagged VLAN the host terminates itself

Otherwise Neutron can allocate a tag the host already owns, leaving two owners
of one VLAN on the same wire. Narrow the range rather than relying on
allocation order; narrowing does not revoke tags already assigned, so check for
existing collisions when you do.

Dedicated ports avoid this — the two trunks are physically separate.

## MTU

`global_physnet_mtu` sets what Neutron advertises. The path must carry that
plus 4 bytes for the VLAN tag, end to end, including the switch ports.

## Verification

Before deploying OpenStack onto the cluster:

```bash
ovs-vsctl show                  # the bridge exists and has an uplink port
ip -br addr                     # no host addresses on the bridge
```

Then, with the deployment up:

- Create a provider network and pass traffic on its tag.
- Create a **second** provider network afterwards and pass traffic on its tag
  too. A path that works for the tag present at configuration time but not for
  a later allocation is the most common way this requirement is met only
  partially.
- Fail one uplink member and confirm both the host path and the bridge path
  survive.
