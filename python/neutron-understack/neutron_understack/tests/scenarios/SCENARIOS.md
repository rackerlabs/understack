# ML2 mechanism scenario catalog

This is the human-readable **test plan** for the `neutron-understack` ML2 mechanism
drivers. Each scenario below has a stable ID and describes the operation it models
and the **mechanism calls + data** we expect to observe.

Every scenario here must be implemented by at least one test tagged
`@pytest.mark.scenario("<ID>")`, and every such marker must reference a scenario
that exists here. `test_scenario_coverage.py` enforces this equivalence in both
directions, and `conftest.py` fails the run if any scenario test is missing a
marker. So this file and the tests cannot silently drift apart.

Scenario IDs are declared as `### <ID> — <title>` headings. Ideas under
"Planned / future" are intentionally *not* IDs (no `###` heading) so they are not
treated as catalogued-but-untested.

## Baremetal port binding (Ironic vif-attach)

Runtime chain: `mechanism_drivers = ovn,understack,baremetal,undersync`. These
scenarios load `logger,understack,undersync` (OVN is only needed for router
scenarios). Tenant networks are VXLAN; the physnet named in the binding profile
(`physnet1` in tests) is a VLAN group.

### BM-BIND-01 — baremetal vif-attach binds hierarchically
- given: a VXLAN tenant network and an unbound baremetal port
- when: the port is updated with `binding:host_id` + a binding profile carrying
  `physical_network=<physnet>` and `local_link_information` (the Ironic vif-attach)
- then:
  - `understack` binds the VXLAN segment and hands down a dynamically allocated
    VLAN segment on `<physnet>` (`continue_binding`)
  - `undersync` binds that VLAN segment (`set_binding`, `vif_type=OTHER`,
    `status=ACTIVE`)
  - two binding levels result: level 0 driver `understack` (VXLAN),
    level 1 driver `undersync` (dynamic VLAN)
  - `undersync.sync(<physnet>)` reconciles the switch

### BM-BIND-02 — vif-attach without physical_network refuses binding
- given: a VXLAN tenant network and an unbound baremetal port
- when: vif-attach supplies a binding profile with **no** `physical_network`
- then: `understack` refuses to bind (no `continue_binding`), the port ends
  `binding:vif_type=binding_failed` with no binding levels, and
  `undersync.sync` is not called

### BM-BIND-03 — unsupported vnic_type is not bound by us
- given: a VXLAN tenant network and a port with an unsupported vnic_type
  (e.g. `direct`)
- when: vif-attach is attempted
- then: neither `understack` nor `undersync` binds it (`binding_failed`), and
  `undersync.sync` is not called

### BM-BIND-04 — vif-detach unbinds, reconciles, and releases the VLAN segment
- given: a bound baremetal port (per BM-BIND-01)
- when: the binding is cleared (`binding:host_id=""`, empty profile)
- then: the port returns to `binding:vif_type=unbound`,
  `undersync.sync(<physnet>)` reconciles the switch, and the dynamic VLAN segment
  is **released** so its VLAN id returns to the pool
- status: **KNOWN BUG (xfail)** — the driver does not release the segment on
  detach today (see "Known bugs"). The test asserts the desired behavior and is
  marked `xfail(strict=True)`, so it will start failing (prompting removal of the
  xfail) once the bug is fixed.

### BM-BIND-05 — port delete releases the dynamic VLAN segment
- given: a bound baremetal port (per BM-BIND-01)
- when: the port is deleted
- then: the dynamic VLAN segment is released (no ports remain bound to it) and
  `undersync.sync(<physnet>)` reconciles the switch

### BM-BIND-06 — vif-attach with no IP still emits the physnet sync
- given: a VXLAN network with a subnet, and a baremetal port created with no
  fixed IP (`fixed_ips: []`)
- when: the port is vif-attached (host + profile with `physical_network`)
- then: the port binds and `undersync.sync(<physnet>)` still fires — the sync
  does not depend on the port having an IP

## Trunk subport operations

These scenarios load the real neutron trunk service plugin
(`UnderstackMl2TrunkScenarioBase`). The parent is a bound baremetal port; subport
adds/removes must reconcile the parent's switch (VLAN group).
`utils.fetch_network_node_trunk_id` (live OVN + Ironic discovery) is stubbed.

### TRUNK-SUB-ADD — subport attach syncs the parent's physnet
- given: a bound baremetal parent port on `physnet1` with a trunk, and a subport
  port on another network
- when: the subport is added to the trunk (VLAN segmentation)
- then: `undersync.sync(physnet1)` reconciles the parent port's switch

### TRUNK-SUB-DEL — subport removal syncs the parent's physnet
- given: the TRUNK-SUB-ADD setup with the subport attached
- when: the subport is removed from the trunk
- then: `undersync.sync(physnet1)` reconciles the parent port's switch

### TRUNK-PARENT-NOIP — subport add syncs when the parent has no IP
- given: a bound baremetal parent on a subnetted network but with no fixed IP,
  plus a trunk and a subport on another network
- when: the subport is added
- then: `undersync.sync(physnet1)` still fires — a parent with no IP does not
  suppress the reconcile

## Router interface (VRF flavor)

These scenarios load a real L3 router + flavors plugin (`ML2TestFramework`). The
VRF (flavored) router path skips the OVN uplink work, so no OVN IDL fake is
needed. The flavored path is simulated by patching `routers._router_has_flavor`,
mirroring the existing unit tests.

### VRF-RTR-01 — VRF router attach syncs bound baremetal port physnets
- given: a VXLAN network + subnet with baremetal ports bound to two different
  physnets (`physnet1`, `physnet2`)
- when: a VRF router is created and the subnet is attached on the internal side
- then: undersync syncs each physnet carrying the network's baremetal ports so
  the switches are reconciled for the new router
- status: **KNOWN BUG (xfail, rackerlabs/understack#2240)** — attaching the VRF
  router interface does not sync those physnets today (`undersync.sync` is never
  called for them). The test asserts the desired behavior and is
  `xfail(strict=True)`.

### SVI-RTR-01 — SVI router attach syncs bound baremetal port physnets
- given: a VXLAN network + an address-scoped IPv4 subnet, with baremetal ports
  bound to two different physnets (`physnet1`, `physnet2`)
- when: an SVI router is created and the subnet is attached on the internal side
- then: undersync syncs each physnet carrying the network's baremetal ports so
  the switches are reconciled for the new router
- status: **KNOWN BUG (xfail, rackerlabs/understack#2240)** — the same gap as
  VRF-RTR-01 for the SVI flavor: attaching the SVI router interface does not
  sync those physnets today. The SVI flavor is simulated by patching
  `_router_has_flavor` and `svi._is_svi_router`; the subnet is address-scoped so
  the SVI precommit scope validation passes.

## Known bugs (surfaced by these tests)

- **Dynamic VLAN segment leaks on vif-detach** (BM-BIND-04, `xfail`,
  rackerlabs/understack#2239). On the
  bound→unbound update, `_tenant_network_port_cleanup` releases
  `original_top_bound_segment` — the VXLAN segment, which is not dynamic — instead
  of the dynamic VLAN segment at the bottom binding level. So
  `release_segment_if_unused` no-ops and the VLAN segment (and its VLAN id) is
  never freed on detach. It is only released on port **delete**
  (`_delete_port_baremetal`, BM-BIND-05), which contradicts the comment there that
  says detach "normally" releases it. Result: VLAN ids leak whenever a port is
  unbound without being deleted. Fix should release the dynamic (bottom) segment
  on the detach transition; the xfail flips to a pass once fixed.

## Planned / future (not yet catalogued IDs)

- Router create + `add_router_interface`: assert the `network:router_interface`
  port is created and `UnderstackDriver.create_port_postcommit` →
  `routers.create_port_postcommit` runs with the expected data. Requires faking
  the OVN IDL (`neutron_understack.routers.ovn_client()`).
- Trunk parent/subport binding: assert per-subport dynamic VLAN allocation and
  `undersync.sync` calls.
