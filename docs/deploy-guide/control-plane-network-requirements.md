# Control Plane Network Requirements

What UnderStack needs from the networking on the nodes running the control
plane. How you build it is out of scope — these are the requirements the
deployment assumes.

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
network from the configured segment range, and `ovn-controller` adds a localnet
port carrying that tag to the bridge named in `ovn_bridge_mappings`.

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

Two ways to provide the uplink:

- **Dedicated ports.** A second bonded port pair, given to the bridge. Real
  LACP on both bonds, genuine bandwidth isolation, and the whole PF is
  available to `vfio-pci` if you later move to OVS-DPDK. Preferred where the
  ports exist.
- **SR-IOV virtual functions.** Where the nodes have only two ports cabled,
  carve the uplink out of them: host on the PF bond, bridge on one VF per PF.
  Workable, with constraints worth knowing before you commit to it:

    - A VF cannot run LACP, so the bridge's bond cannot be `802.3ad`. If the
      two ports are one LACP port-channel, the OVS bond must be `balance-slb`;
      `active-backup` drops frames arriving on the inactive member, which the
      upstream switch's hashing guarantees will happen.
    - Each VF must be set `trust on` and `spoofchk off`, with no VF VLAN.
      Legacy SR-IOV has no per-VF trunk allow-list, so `trust on` — which also
      makes the VF VLAN-promiscuous — is the only mechanism that carries a
      trunk into a VF. Setting a VF VLAN breaks the trunk.
    - If the bonded ports are on separate cards, the bridge needs a VF on each.
      A VF's MAC exists only in its own card's embedded switch, so a single VF
      loses return traffic the switch hashes to the other card.
    - Isolation is logical, not physical: both bonds share the same ports, so
      there is no dedicated bandwidth.

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
plus 4 bytes for the VLAN tag, end to end, including the switch ports. On an
SR-IOV uplink note that a VF's MTU cannot exceed its PF's.

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
