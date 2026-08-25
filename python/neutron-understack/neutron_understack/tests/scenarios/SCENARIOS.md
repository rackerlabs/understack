# ML2 mechanism scenario catalog

This is the human-readable **test plan** for the `neutron-understack` ML2 mechanism
drivers. Each scenario below has a stable ID and describes the operation it models
and the **mechanism calls + data** we expect to observe.

Every scenario here must be implemented by at least one test tagged
`@pytest.mark.scenario("<ID>")`, and every such marker must reference a scenario
that exists here. `conftest.py` validates collected markers and enforces this
equivalence whenever the complete scenario package is collected. So this file
and the tests cannot silently drift apart in the scenario CI run.

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

### BM-BIND-REUSE-01 — second port on same network+physnet reuses the VLAN seg
- given: a VXLAN network with one bound baremetal port on `physnet1`
- when: a second baremetal port on the same network is vif-attached to `physnet1`
- then: it reuses the existing dynamic VLAN segment (same segment id), no new
  allocation

### PROV-BIND-01 — provisioning-network port binds
- given: a network configured as `ml2_understack.provisioning_network`
- when: a baremetal port on it is vif-attached
- then: it binds hierarchically and `undersync.sync(<physnet>)` fires (no special
  casing on the bind path)

### PROV-DEL-01 — provisioning-network delete retains the VLAN segment
- given: a bound baremetal port on the provisioning network
- when: the port is deleted
- then: `undersync.sync(<physnet>)` fires but the dynamic VLAN segment is
  retained (the clean/provision cycle reuses it), unlike a tenant port
  (BM-BIND-05)

## Trunk subport operations

These scenarios load the real neutron trunk service plugin
(`UnderstackMl2TrunkScenarioBase`). The parent is a bound baremetal port; subport
adds/removes must reconcile the parent's switch (VLAN group).
`utils.fetch_network_node_trunk_id` (live OVN + Ironic discovery) is stubbed.

### TRUNK-SUB-ADD — subport attach syncs the parent's physnet
- given: a bound baremetal parent port on `physnet1` with a trunk, and a subport
  port on another network
- when: the subport is added to the trunk (VLAN segmentation)
- then: the trunk records the subport, a level-0 `understack` binding points it
  at a dynamic VLAN segment on `physnet1`, and `undersync.sync(physnet1)`
  reconciles the parent port's switch

### TRUNK-SUB-DEL — subport removal syncs the parent's physnet
- given: the TRUNK-SUB-ADD setup with the subport attached
- when: the subport is removed from the trunk
- then: the trunk result no longer contains the subport, its synthetic binding
  level is deleted, its now-unused dynamic VLAN segment is released, and
  `undersync.sync(physnet1)` reconciles the parent port's switch

### TRUNK-PARENT-NOIP — subport add syncs when the parent has no IP
- given: a bound baremetal parent on a subnetted network but with no fixed IP,
  plus a trunk and a subport on another network
- when: the subport is added
- then: the subport binding and dynamic segment are created and
  `undersync.sync(physnet1)` still fires — a parent with no IP does not suppress
  the reconcile

### TRUNK-DEL-01 — trunk delete syncs the parent's physnet
- given: a bound baremetal parent with a trunk and an attached subport
- when: the trunk is deleted
- then: the trunk is gone, the subport binding and now-unused dynamic segment
  are deleted, the parent switchport is cleaned, and `undersync.sync(physnet1)`
  fires

### TRUNK-MULTI-01 — adding multiple subports syncs the parent's physnet
- given: a bound baremetal parent with a trunk
- when: two subports on different networks are added in one operation
- then: each subport has its own level-0 binding to a dynamic VLAN segment on
  `physnet1`, the segments are distinct, and `undersync.sync(physnet1)` fires

### TRUNK-PARENT-UNBOUND-01 — subport add with an unbound parent is a no-op
- given: an unbound (plain) parent port with a trunk
- when: a subport is added
- then: trunk membership is recorded, but no subport binding level or dynamic
  VLAN segment is created and no `undersync.sync` occurs

### TRUNK-SEGID-RANGE-01 — subport seg_id outside the allowed range is rejected
- given: a bound baremetal parent with a trunk
- when: a subport is added with a segmentation_id outside `[1, 3799]`
- then: `SubportSegmentationIDError` (raised in the SUBPORTS PRECOMMIT_CREATE
  callback, surfaced as `CallbackFailure`), with no binding level or dynamic
  segment allocated

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

### VRF-DETACH-01 — VRF router detach syncs bound baremetal port physnets
- given: a VXLAN network with baremetal ports on two physnets and an attached
  VRF router interface
- when: the router interface is removed
- then: undersync should sync each physnet still carrying baremetal ports
- status: **KNOWN BUG (xfail, rackerlabs/understack#2240)** — the teardown
  counterpart of VRF-RTR-01; detach does not sync those physnets today.

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

### SVI-VAL-NOSCOPE-01 — SVI rejects a subnet with no address scope
- given: an SVI router and a subnet not in any address scope
- when: the subnet is attached on the internal side
- then: the attach is rejected (the SVI precommit validator raises BadRequest,
  which the ML2 manager surfaces as MechanismDriverError)

### SVI-VAL-IPV6-01 — SVI rejects an IPv6 subnet
- given: an SVI router and an IPv6 subnet
- when: the subnet is attached
- then: the attach is rejected (SVI routers are IPv4-only)

### SVI-VAL-CONFLICT-01 — SVI rejects conflicting address scopes
- given: an SVI router with an interface in address scope A
- when: a subnet in a different scope B is attached
- then: the attach is rejected (per-IP-version scope conflict)

## Router uplink (non-flavored, OVN)

These load an L3 router + flavors + trunk plugin
(`UnderstackMl2RouterOvnScenarioBase`) and patch `routers.ovn_client` with a
`FakeOvnClient` (records localnet LSP create/delete; short-circuits the vxlan
HCG workaround). `utils.fetch_network_node_trunk_id` is mocked to a trunk the
test creates.

### RTR-ATTACH-01 — non-flavored router attach builds the uplink
- given: a network+subnet, a network-node trunk, and a non-flavored router
- when: the subnet is attached on the internal side
- then: a dynamic VLAN uplink segment is allocated on the network-node physnet;
  the shared `uplink-` neutron port, trunk subport tag, and OVN localnet LSP tag
  all reference that segment and VLAN on the network's logical switch

### RTR-SECOND-01 — second router on the same network is a no-op
- given: a network with two subnets, the first already attached to a router
- when: a second router attaches the second subnet
- then: no new uplink is built (`is_only_router_port_on_network` is false)

### RTR-DETACH-01 — remove_router_interface tears down the uplink
- given: a network with a router interface and its uplink
- when: the interface is removed
- then: the shared port is removed from the network-node trunk, both the
  `uplink-<segment-id>` localnet LSP and shared-port LSP are deleted from the
  exact logical switch, and the shared `uplink-` neutron port is removed

## Router flavor providers (Palo Alto)

These register the Palo Alto provider as an L3 service provider and create a real
flavor + service profile (`driver` = the PaloAlto class, `metainfo.resource_class`
= the netdev pool). `IronicClient` is faked (single-node pool).

### PALO-ADOPT-01 — Palo Alto router adopts an Ironic netdev node
- given: the Palo Alto provider registered and a matching flavor
- when: a router with that flavor is created
- then: the ROUTER BEFORE_CREATE callback adopts the available netdev node for
  the router (via the faked Ironic client)

### PALO-RELEASE-01 — deleting a Palo Alto router releases its node
- given: a Palo Alto router that adopted a node
- when: the router is deleted
- then: the ROUTER AFTER_DELETE callback returns the node to the pool

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

## Backlog (not yet covered)

Proposed scenarios, grouped by area. These are intentionally plain bullets (not
`###` IDs) so the coverage check does not treat them as catalogued-but-untested;
promote a bullet to a `### <ID>` heading when its test lands.

Port create / bind / delete (no new test doubles):
- BM-REBIND-01 — rebind on `binding:host_id` change.
- BM-DEL-NOPHYSNET-01 — delete a bound port whose profile lost `physical_network`
  (early return, no sync).

Trunk (no new test doubles):
- TRUNK-CREATE-WITH-SUBPORTS-01 — trunk created with subports present
  (`trunk_created` path); confirm whether it syncs (it may not — possible gap).
- TRUNK-PARENT-UNBIND-01 — unbinding a trunked baremetal parent runs `clean_trunk`
  (subport teardown) alongside BM-BIND-04's segment handling.
- TRUNK-NOPHYSNET-01 — subport add/remove on a parent with no `physical_network`.
  Not reachable via normal binding (a baremetal port cannot bind without a
  physnet), so needs an artificially mutated binding profile.

SVI validation:
- SVI-EXTGW-01 — an SVI router cannot get an external gateway. Needs the real
  Svi provider + flavor wiring (the `_reject_svi_external_gateway` callback),
  which the patched-flavor scenarios do not load.

Router (needs an OVN IDL fake for `routers.ovn_client()`):
- RTR-DELETE-01 — `delete_router` cleanup via `handle_router_interface_removal`
  (PORT PRECOMMIT_DELETE). Not reachable with the standard L3 plugin, which
  raises RouterInUse unless interfaces are removed first; needs a trigger that
  deletes a router-interface port directly.
- RTR-HCG-VXLAN-01 — `link_vxlan_network_ha_chassis_group` populates the unified
  HCG for a vxlan external gateway (needs a deeper OVN NB/SB fake).

VNI:
- VNI-ALLOC-01 — VRF router create/delete allocates/releases an `evpn_vni`
  (`UnderstackVniPlugin`). Needs the understack_vni service plugin loaded, its
  `understack_router_vni_allocations` table created (import the model so the
  SQLite fixture builds it), and a flavor whose service-profile metainfo sets
  `vni_alloc`. The Vrf/UserDefined provider it pairs with may pull in OVN L3 on
  router create, so it likely also needs the OVN fake.

Cross-cutting:
- DRYRUN-01 — `undersync_dry_run=True` routes to dry-run instead of sync. This
  branch lives inside `Undersync.sync()` (an HTTP-client detail) which the
  scenarios mock, so it has no scenario-observable effect; better unit-tested.

Explicitly out of scope: Cisco ASA floating-IP NAT.
