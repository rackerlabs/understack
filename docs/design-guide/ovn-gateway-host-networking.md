# OVN Gateway Host Networking

## Status

This document proposes a two-bridge Open vSwitch (OVS) topology for OVN
gateway nodes that have only two connected network interfaces. It has not yet
been deployed.

The design prioritizes provider-network performance while separating the
host-owned physical uplink from the OVN-owned provider bridge. It does not
remove OVS from the host management path. Four connected interfaces remain
the preferred topology when they are available.

## Scope

This design applies when two data-center-facing interfaces must carry both:

- a dedicated host network for the node address, default route, Kubernetes,
  Cilium, and keepalived; and
- tagged provider traffic for VLAN segments dynamically allocated by Neutron
  and used by OVN.

The host network may be tagged or native/untagged on the physical fabric. A
tagged-only switch trunk is preferred for new deployments. Supporting a native
host network eases migration of existing deployments without changing the OVS
bridge topology.

The two interfaces connect to separate adapters and switch failure domains
where available and form one LACP LAG across the switch pair.

With four connected interfaces, use the traditional topology:

- two interfaces in a Linux LACP bond for the host OS and Kubernetes; and
- two interfaces in a separate OVS LACP bond for OVN provider traffic.

| Connected interfaces | Host attachment | OVS attachment | Use |
| --- | --- | --- | --- |
| Four | Two-PF Linux LACP bond | Separate two-PF OVS LACP bond | Preferred |
| Two | Host-owned OVS bridge | Shared two-PF OVS LACP bond | Performance-oriented fallback |

## Problem

The current two-interface topology puts the physical OVS bond, host IP, and
OVN provider connectivity on the same bridge:

``` mermaid
flowchart LR
    switches["Leaf switch pair"] --> pf1["NIC PF 1"]
    switches --> pf2["NIC PF 2"]
    pf1 --> ovsBond["OVS bond0<br/>LACP"]
    pf2 --> ovsBond
    ovsBond --> brEx["OVS br-ex"]
    brEx --> host["Host IP, default route,<br/>Kubernetes"]
    brEx --> ovn["OVN provider traffic"]
```

This provides a direct, high-performance path from OVS to the physical NICs,
but gives one bridge two owners. Host networking treats `br-ex` as its
primary interface while OVN treats it as the provider bridge. Changes intended
for the OVN data path can therefore affect the host management path and
physical LAG.

SR-IOV does not provide a supported escape from this ownership conflict when
the two ports are on separate NIC controllers. A VF belongs to one PF and does
not inherit redundancy from a Linux bond above that PF. Bonding VFs from
separate PFs is not a generally supported substitute for NIC and driver VF-LAG
support.

## Goals

- Preserve the direct OVS-to-PF data path for provider-network performance.
- Preserve active-active LACP across separate adapters and switches.
- Give the physical LAG and host interface a host-owned bridge that OVN does
  not manage.
- Keep the OVN bridge mapping on a dedicated `br-ovn` bridge.
- Carry the host network and tagged provider networks over the same LAG without
  admitting the host network to `br-ovn`.
- Allow Neutron to allocate VLANs dynamically without changing host networking
  for each allocation.
- Make ownership, startup ordering, and recovery requirements explicit.

The two-interface topology cannot keep OVS out of the host management path.
That requires four connected interfaces or accepting a Linux bridge and veth
in the provider data path.

## Decision

For the two-interface, performance-oriented topology, host-installed OVS owns
both physical interfaces and the LACP bond. The bond belongs to a host-owned
bridge named `br-host`. The node address is configured on the OVS internal
interface that OVS creates for `br-host`. A tagged trunk over an OVS
patch-port pair connects `br-host` to the `br-ovn` provider bridge used by
OVN.

The name `br-host` makes ownership clear: this bridge and its same-named
internal interface provide the node's host network. Although `br-ex` is a
common OpenStack convention, `br-ovn` makes this design's ownership boundary
explicit.

``` mermaid
flowchart LR
    switches["Leaf switch pair<br/>host + provider VLAN trunk"] --> pf1["NIC PF 1"]
    switches --> pf2["NIC PF 2"]
    pf1 --> ovsBond["OVS bond0<br/>balance-tcp + LACP"]
    pf2 --> ovsBond
    ovsBond --> brHost["OVS br-host<br/>host-owned"]
    brHost --> host["Internal interface br-host<br/>host IP, default route,<br/>Kubernetes"]
    brHost <-->|"tagged provider trunk<br/>OVS patch pair"| brOvn["OVS br-ovn<br/>OVN provider bridge"]
    brOvn <--> brInt["OVS br-int / OVN"]
```

The logical OVS objects are:

| Object | Type | Owner | Purpose |
| --- | --- | --- | --- |
| `br-host` | OVS bridge and internal interface | Host networking | Physical fabric and host network |
| `bond0` | OVS port with two member interfaces | Host networking | LACP attachment to the switch pair |
| `patch-host` | OVS patch port | Host networking | Provider trunk toward `br-ovn` |
| `br-ovn` | OVS bridge | Host networking | Bridge mapped to the Neutron physnet |
| `patch-ovn` | OVS patch port | Host networking | Provider trunk toward `br-host` |

OVN bridge mappings continue to reference an OVS bridge:

``` text
PHYSICAL_NETWORK:br-ovn
```

OVN does not map a physnet directly to `bond0`. An OVS bond is a port that
must belong to an OVS bridge.

`bond0` uses `bond_mode=balance-tcp` and `lacp=active`. Where the switch LAG
forwards on an individual member when LACP is absent, `bond0` also sets
`other_config:lacp-fallback-ab=true`. If the partner then stops sending
LACPDUs, such as during switch misconfiguration or maintenance, the bond falls
back to active-backup on one member so the host remains reachable. Where the
switch policy suspends members without LACP, the fallback has no effect and is
not relied on.

## Ownership Boundary

`br-host`, `bond0`, `br-ovn`, and both ends of the host-to-OVN patch pair are
persistent host-networking configuration. OVN must not create, replace, or
modify them.

`br-ovn` is reserved for OVN provider connectivity. Its internal interface
has no host IP address, including an IPv6 link-local address, and no default
route, router advertisement acceptance, DNS configuration, Cilium selection, or
keepalived address. OVN only adds and removes its own patch ports between
`br-int` and `br-ovn`.

This is a configuration ownership boundary, not a process or failure boundary.
Both bridges use the same host OVS database, daemon, and datapath. An OVS
failure can still disconnect the host.

## VLAN Policy

The host network and Neutron provider ranges are separate allocations. The
host VLAN must not be included in a Neutron provider range, and no host
address is configured on a provider VLAN.

Tagged host networking is preferred. In this mode:

- the switch LAG has no native VLAN and carries the host VLAN and provider
  ranges as tagged traffic;
- `bond0` trunks the host VLAN and provider ranges;
- the `br-host` internal interface is an OVS access port on the host VLAN, so
  the host OS uses a normal, untagged interface; and
- untagged traffic received from the physical fabric is not admitted.

A deployment may instead carry the host VLAN as native/untagged traffic during
migration. The physical OVS bond classifies that traffic into the host VLAN,
while the same `br-host` internal access port presents it untagged to the host
OS. This is a wire-mode difference and does not change bridge ownership.

In both modes, `patch-host` and `patch-ovn` explicitly trunk only the provider
ranges. They exclude the host VLAN and VLAN 0, so neither tagged host traffic
nor native/untagged traffic can reach `br-ovn`.

The OVS port settings are:

| Port | Tagged host network | Native host network |
| --- | --- | --- |
| `bond0` | `vlan_mode=trunk`, `trunks=HOST,PROVIDER` | `vlan_mode=native-untagged`, `tag=HOST`, `trunks=PROVIDER` |
| `br-host` | `vlan_mode=access`, `tag=HOST` | `vlan_mode=access`, `tag=HOST` |
| `patch-host`, `patch-ovn` | `vlan_mode=trunk`, `trunks=PROVIDER` | `vlan_mode=trunk`, `trunks=PROVIDER` |

A native-untagged port always carries its native VLAN, so `HOST` is omitted
from its `trunks`. OVS treats an empty `trunks` column as all VLANs, so an
unset trunk list on the patch pair admits the host VLAN to `br-ovn`.

| Path | Host network | Provider VLAN ranges |
| --- | --- | --- |
| Switch LAG and OVS `bond0` | Tagged preferred; native/untagged supported | Tagged trunk |
| Internal interface `br-host` | OVS access port; untagged to the host OS | Not admitted |
| Patch pair | Not admitted | Tagged trunk |
| OVN `br-ovn` | Not admitted | Tagged trunk |

Neutron Network Segment Ranges are the source of truth for provider ranges.
Deployment inventory supplies the host VLAN, its wire mode, and the provider
ranges without embedding site-specific allocations in this design. The switch
LAG and OVS trunks must admit the required ranges before Neutron allocates from
them. Dynamic allocation then requires no per-network Netplan or OVS update.

See [Neutron Networking](neutron-networking.md) for the dynamic VNI-to-VLAN
allocation model.

## Host Networking and Lifecycle

The following use the `br-host` internal interface:

- the node's primary address and default route;
- DNS configuration;
- the Kubernetes node address;
- the OVN Geneve encapsulation address (`ovn-encap-ip`);
- Cilium's direct-routing device selection; and
- keepalived addresses and interface selection.

Cilium native XDP acceleration is not used on these nodes; the `br-host` OVS
internal interface does not support native XDP.

MTU must be consistent across the physical interfaces and the `br-host`
internal interface, which is set explicitly rather than derived by OVS. Patch
ports have no MTU of their own; provider traffic is bounded by the physical
MTU. The required MTU is an inventory value selected to meet the deployment's
provider-network requirements.

Because the host IP depends on OVS, OVS must be installed and managed by the
host OS. Its database and datapath must be available before services that need
the node network. Running the only OVS control processes as ordinary Kubernetes
workloads would create a recovery cycle: Kubernetes needs the node network to
recover the workload that creates the node network.

The host-networking Ansible role renders configuration but does not configure
OVS directly. Netplan creates `br-host`, `bond0`, an empty `br-ovn`, and host
addressing. A deployment-owned, idempotent systemd service creates the patch
pair and applies the port settings Netplan cannot express: `tag`, `vlan_mode`,
and `trunks`. Reboot is realized by Netplan and this service without Ansible,
and Ansible changes take effect through the same path. OVN deployment must not
construct or modify the physical fabric path.

The patch pair is created fail-closed. Each patch port is created with its
peer, `vlan_mode`, and provider `trunks` in a single OVSDB transaction and is
never modified to an empty `trunks`. On initial deployment, `br-host` and
`br-ovn` are not connected until the service runs, so a delayed or failed
service stops provider forwarding rather than admitting the host VLAN. Once
created, the patch pair also persists in OVSDB: on later boots a failed
service leaves the last persisted, restricted patch pair in place, and
disabling the service alone does not disconnect the bridges. OVN's own patch
ports on `br-ovn` persist in OVSDB across reboots, so isolation cannot depend
on `ovn-controller` starting after the service.

The service is ordered after OVS is running and before
`network-online.target`, waits with a bounded timeout for the Netplan-created
bridges, and reapplies its settings after any Netplan change. The design does
not depend on generated Netplan unit names or on how Netplan treats settings
it did not create. `netplan apply` can reconfigure the bond, so it is treated
as disruptive and applied only when the rendered configuration changes.

Restarting `openvswitch-switch` is expected to interrupt forwarding briefly
and restore host networking from OVSDB without Netplan, Ansible, or
Kubernetes. Retention of the `br-host` internal interface, its addresses, and
datapath state across the restart is verified on the canary rather than
assumed.

### Health and Recovery

The operating-system OVS package and systemd units supervise `ovsdb-server`
and `ovs-vswitchd`. The deployment also installs a host-local systemd service
and timer that validate the realized topology, not merely the daemon process
state. The check must not depend on Kubernetes, DNS, Git, or access to the
Ansible controller.

The local check validates at least:

- OVSDB responsiveness and the `ovs-vswitchd` connection to it;
- the existence of `br-host`, `br-ovn`, the physical bond, and the patch pair;
- the expected bond members and at least one usable member;
- valid realized ports for the internal, physical, and patch interfaces; and
- the host and provider VLAN policy against desired state rendered locally by
  Ansible, treating an empty patch-pair `trunks` column as a failure.

Recovery is bounded and escalates through retry, restart of only the failed OVS
service, and an idempotent local topology reconciliation. Reconciliation reruns
the deployment service rather than maintaining a separate copy of the
desired topology. Repeated failure must
stop automatic repair and leave diagnostic state intact for external monitoring
and out-of-band recovery. Loss of physical links is reported without restarting
otherwise healthy OVS services. The checker must not recreate a corrupt OVS
database or reboot a host solely because remote network probes fail.

External reachability monitoring, alerting, and BMC-driven recovery are
deployment monitoring responsibilities outside this design.

## Performance

Provider traffic traverses the OpenFlow pipelines of `br-ovn` and `br-host`
across the OVS patch pair and leaves directly through a physical bond member.
It does not traverse a Linux bridge, veth pair, SR-IOV VF, or userspace
forwarding process.

The patch pair is a logical boundary inside OVS. `ovs-vswitchd` resolves
patch ports during flow translation rather than forwarding through a separate
device, so it avoids the device traversal a Linux veth pair adds. Geneve
traffic uses the host network on `br-host`, not the patch pair. Qualification
must still compare this topology with the current single-bridge path at the
required throughput, packet rate, flow count, VLAN count, and MTU. Hardware
flow offload and OVS-DPDK are separate qualification work and are not required
here.

Qualification covers bidirectional single-flow and many-flow traffic at
multiple packet sizes and representative VLAN and flow scale. Sustained
throughput and packet rate must each reach at least 95 percent of the qualified
single-bridge baseline. Latency and host CPU consumption must remain within
the deployment's existing performance SLOs at equivalent offered load.

Physical-link and leaf-switch failure tests must restore host and provider
forwarding within the convergence interval implied by the configured LACP
detection timers. Repeated failure and recovery must not leave the bond
degraded or require manual OVS repair.

## Failure Behavior

| Failure | Expected effect |
| --- | --- |
| One physical link or leaf switch fails | OVS LACP bond continues on the surviving member. |
| `ovn-controller` or OVN connectivity fails | Provider forwarding may fail; `br-host` remains host-owned. |
| LACP is not negotiated | With switch support for individual members, `bond0` falls back to active-backup on one member at reduced capacity; otherwise the bond is down. |
| `br-ovn` or the patch pair is removed | Provider forwarding fails until the topology check or reboot restores it; host configuration remains on `br-host`, provided OVS remains healthy. |
| `openvswitch-switch` is restarted | Host and provider connectivity briefly fail and are expected to recover from OVSDB without intervention. |
| Patch-pair service is delayed or fails on initial deployment | `br-host` and `br-ovn` remain unconnected; provider forwarding fails and host networking is unaffected. |
| Patch-pair service fails on a later boot | The last persisted, restricted patch pair remains in place; drift from desired state is reported by the topology check. |
| OVS daemon, database, or datapath fails | Host and provider connectivity can both fail. |
| Host-VLAN or untagged traffic leaks onto the patch pair | Design violation; host traffic may enter `br-ovn`. |
| Both physical links fail | Host and provider traffic fail. |

Multiple gateway chassis and OVN scheduling remain responsible for
service-level gateway HA. The local LACP bond protects only this node's
physical attachment.

## Four-Interface Topology

When four interfaces are connected, do not use the shared `br-host` design
merely for consistency. Use independent physical bonds:

``` mermaid
flowchart LR
    hp1["Host NIC 1"] --> linuxBond["Linux host bond<br/>802.3ad"]
    hp2["Host NIC 2"] --> linuxBond
    linuxBond --> host["Host IP and Kubernetes"]
    op1["OVN NIC 1"] --> ovsBond["OVS provider bond<br/>LACP"]
    op2["OVN NIC 2"] --> ovsBond
    ovsBond --> brOvn["OVS br-ovn"]
```

This is the control-plane hardware target because OVS cannot remove host
connectivity and provider traffic retains direct physical interfaces.

## Alternatives

### Single shared `br-ex`

Putting the host IP, physical bond, and OVN provider mapping on `br-ex` has
the shortest configuration and data path. It is not selected because the
physical fabric and host management interface share the bridge OVN uses for
provider networking.

### Linux bond, Linux bridge, and veth

A Linux LACP bond beneath a VLAN-aware Linux bridge can give the host an
OVS-independent management path. A veth pair connects the provider trunk to
OVS. This is the hardware-neutral, isolation-oriented fallback, but adds Linux
bridge and veth traversal to provider traffic.

### SR-IOV VF sharing

Giving OVS one VF from each adapter does not make the VFs inherit the PF Linux
bond. Software bonding of VFs is not a supported replacement for driver and
firmware VF-LAG, and supported VF-LAG may require both ports on the same NIC
controller. Trusted-promiscuous VF, arbitrary-MAC, VLAN-trunk, reset, and
firmware behavior would also need qualification. This approach is rejected for
the general two-card topology.

### OVS-DPDK

OVS-DPDK can dedicate physical devices to userspace forwarding, but does not
solve the ownership conflict: the host still needs a path over the same two
ports. It also adds CPU, NUMA, lifecycle, and operational requirements outside
this design.

## Migration Plan

This change can sever Kubernetes and administrative access. Migrate one canary
at a time with working console access and a tested rollback procedure.

1. Record the switch LAG, host VLAN and wire mode, provider ranges, Neutron
   segment ranges, routes, addresses, Cilium selection, and keepalived
   configuration.
2. Confirm both switch ports use one LACP LAG with identical VLAN policy. When
   fallback is configured, confirm the LAG forwards on individual members when
   LACP is absent.
3. Build persistent `br-host`, the OVS LACP bond, patch pair, and empty
   `br-ovn` in a test environment.
4. Confirm the patch pair rejects the host VLAN and untagged traffic while
   admitting all provider ranges.
5. Validate the host network in its selected wire mode and tagged provider
   VLANs near both ends of every range.
6. Cordon and drain the canary as appropriate. Draining does not move OVN
   gateway ports, so remove the canary's gateway role and confirm that its
   gateway router ports have failed over before continuing. Otherwise gateway
   ports fail back to the canary when BFD recovers, before its provider
   mapping works. Use console access for the management-address move.
7. In one Netplan change, move the physical OVS bond and host addressing,
   routes, and DNS from `br-ex` to `br-host`, then let the deployment service
   connect `br-host` to `br-ovn` with the restricted patch trunk. Update Cilium
   and keepalived references. Moving the address separately from the bond
   isolates the host.
8. Change the canary's OVN bridge mapping from `br-ex` to `br-ovn`, and
   ensure the OVN deployment does not attach physical interfaces to bridges or
   move addresses. Confirm `ovn-controller` replaces its `br-int` patch ports
   to `br-ex` with ports to `br-ovn`, then remove `br-ex`.
9. Validate host, Kubernetes, OVN provider, north/south routing, link failure,
   LACP fallback where supported, `openvswitch-switch` restart, and reboot
   behavior.
10. Restore the gateway role and confirm gateway router ports schedule to the
    canary before proceeding to the next node.

Rollback reverts both the host networking and the OVN bridge mapping.

The exact commands belong in an environment-specific runbook after the design
is implemented in Ansible. They should not be improvised during production
maintenance.

## Acceptance Criteria

- `ovs-vsctl show` reports both physical interfaces in one LACP bond on
  `br-host`.
- The `br-host` internal interface owns the node address and default route;
  `br-ovn` has no address, including IPv6 link-local.
- The OVN bridge mapping references `br-ovn`, not `br-host` or `bond0`.
- The patch pair rejects the host VLAN and untagged traffic while admitting all
  provider ranges.
- In tagged-only mode, the physical bond rejects untagged ingress.
- Provider networks on multiple dynamically selected VLANs pass traffic.
- Removing either physical link preserves established host and provider
  connectivity and restores forwarding within the configured LACP convergence
  interval.
- Restarting `ovn-controller` does not modify `br-host` or `bond0`.
- OVS starts early enough after reboot to restore host connectivity without
  Kubernetes intervention.
- Reboot restores the complete topology, including patch-pair trunk lists,
  through Netplan and the deployment service without running Ansible.
- With the host patch pair removed and its deployment service disabled, a
  reboot leaves `br-host` and `br-ovn` unconnected and the host network
  operational.
- Restarting `openvswitch-switch` restores host connectivity without
  intervention, and the canary confirms whether interface addresses and
  datapath state are retained.
- Where the switch supports individual members, disabling LACP on the switch
  LAG leaves the host reachable through active-backup fallback.
- The host-local topology check detects a missing required object or unusable
  bond and performs bounded recovery without Kubernetes or external network
  access.
- Exhausted recovery attempts preserve diagnostic state and surface a failure
  to the deployment's external monitoring system.
- A second Ansible run makes no changes.
- Sustained throughput and packet rate each reach at least 95 percent of the
  qualified single-bridge baseline across the required test matrix.
- Latency and host CPU consumption remain within the deployment's existing
  performance SLOs at equivalent offered load.
- Repeated link failure and recovery do not leave the bond degraded or require
  manual OVS repair.

## Future Evaluation

Hardware flow offload and OVS-DPDK are separate performance initiatives.
Neither is a prerequisite or acceptance criterion for this kernel-datapath
design. Each requires its own hardware, driver, failure-mode, lifecycle, and
performance qualification before adoption. OVS-DPDK also requires a separate
design for preserving host connectivity over the shared physical interfaces.

## References

- [Open vSwitch bonding](https://docs.openvswitch.org/en/latest/topics/bonding/)
- [Open vSwitch configuration database](https://www.openvswitch.org/support/dist-docs/ovs-vswitchd.conf.db.5.html)
- [Linux bonding driver](https://docs.kernel.org/networking/bonding.html)
- [OVN provider network architecture](https://docs.openstack.org/neutron/latest/admin/ovn/refarch/provider-networks.html)
