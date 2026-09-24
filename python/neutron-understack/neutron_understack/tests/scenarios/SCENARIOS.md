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

## How the mechanism works (read this first)

If you have never worked on these drivers, read this section before the
scenarios. Every scenario below is phrased in terms of the vocabulary and the
lifecycle described here.

### The problem being solved

A tenant network in UnderStack is a **VXLAN** network: it has one VXLAN segment
with a VNI, and that VNI is the network's identity as far as Neutron and OVN are
concerned. A baremetal server, though, has no vSwitch. Its NIC is cabled into a
physical leaf switch, and the only thing you can tell a physical switchport
about is a **VLAN**.

So for every tenant network that has to reach baremetal, something must pick a
VLAN id *on that particular switch pair* and stretch the VXLAN network onto it.
That something is the `understack` mechanism driver, and the mechanism it uses
is Neutron's **hierarchical port binding**.

### Vocabulary

| Term | What it means here |
| --- | --- |
| **VLAN group**, a.k.a. **physnet** | One pair of leaf switches. Neutron calls it a `physical_network`; we call it a VLAN group. The tests use `physnet1` / `physnet2`. Ironic tells us which VLAN group a baremetal port lives on via `binding_profile["physical_network"]`. |
| **VLAN id pool** | The VLAN ranges configured for a physnet. VLAN ids are only unique *within* a VLAN group, so two switch pairs can independently hand out the same VLAN id for different networks. The pool is finite, which is why leaking VLAN ids matters. |
| **dynamic segment** | A VLAN segment Neutron allocates on demand for one `(network, physnet)` pair and flags `is_dynamic`. It is the VXLAN network's local VLAN representation on that one switch pair. |
| **binding level** | A row in `ml2_port_binding_levels` recording "driver *D* bound port *P* at level *N* to segment *S*". Hierarchical binding produces one row per level. These rows are also what we count to decide whether a segment is still in use. |
| **undersync** | The service that renders and pushes the desired switch configuration. `undersync.sync(<physnet>)` means "go reconcile that VLAN group's switches"; it is a whole-group reconcile, not a per-port delta. |

### The binding chain

The deployed driver order is
`mechanism_drivers = ovn,understack,baremetal,undersync`. For a baremetal
vif-attach the interesting part is:

1. Ironic sets `binding:host_id` and a `binding_profile` on the Neutron port.
   The profile carries `physical_network` (which VLAN group) and
   `local_link_information` (which switch and interface).
2. `understack.bind_port` finds the network's VXLAN segment, obtains the dynamic
   VLAN segment for `(network, physnet)` — see the next section — and calls
   `continue_binding`, handing that VLAN segment down to the next driver.
3. `undersync.bind_port` accepts the VLAN segment and calls `set_binding`
   (`vif_type=OTHER`), which ends the chain.
4. The port now has **two binding levels**: level 0 = `understack` on the VXLAN
   segment, level 1 = `undersync` on the dynamic VLAN segment.
5. `understack.update_port_postcommit` calls `undersync.sync(<physnet>)`, which
   is what actually makes the switch configuration match.

This is why most scenarios assert three things: the binding levels and their
segments (did we model the network correctly?), the segment's allocation state
(did we manage the VLAN pool correctly?), and that `undersync.sync` was called
for the right physnet (did we ask for the switches to be reconciled?).

### The dynamic VLAN segment is shared, so it is reference-counted

This is the single most important thing to understand, and most of the
segment-related assertions below exist to pin it down.

A dynamic VLAN segment belongs to a `(network, physnet)` pair, **not** to a
port. Ten baremetal ports on the same tenant network in the same VLAN group all
share one VLAN id — that is the whole point, they need to be in the same
broadcast domain on that switch pair. So:

- **On the way in, we allocate *or* reuse.** Binding a port looks for an
  existing VLAN segment for that `(network, physnet)` pair. If one exists, the
  port is bound to it and no new VLAN id is taken from the pool. Only if there
  is none do we allocate a new dynamic segment. (See `BM-BIND-REUSE-01`.)
- **On the way out, we release *only if* nothing else is using it.** Unbinding
  or deleting a port must *not* free the VLAN id just because that port is
  gone — its neighbours on the same network and switch pair are still using it.
  The release is conditional: `utils.release_segment_if_unused` frees the
  segment only when no binding level rows still reference it *and* the segment
  is dynamic. If any port (or trunk subport) remains bound to it, the segment
  and its VLAN id stay.

Read every "releases the VLAN segment" phrase below as "releases the VLAN
segment **if and only if** it is dynamic and no other port is still bound to
it". The scenarios that assert a release do so in a setup with a single
consumer, precisely so that the release is the expected outcome.

## Baremetal port binding (Ironic vif-attach)

These scenarios load `logger,understack,undersync` rather than the full
deployed chain (OVN is only needed for the router scenarios). Tenant networks
are VXLAN; the physnet named in the binding profile (`physnet1` in tests) is a
VLAN group.

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

### BM-BIND-04 — vif-detach unbinds, reconciles, and releases the VLAN segment if unused
- given: a bound baremetal port (per BM-BIND-01), and it is the **only** port
  bound to that dynamic VLAN segment
- when: the binding is cleared (`binding:host_id=""`, empty profile)
- then:
  - the port returns to `binding:vif_type=unbound`
  - `undersync.sync(<physnet>)` reconciles the switch
  - the dynamic VLAN segment is **released** — but only because no other port
    is still bound to it. The release is conditional
    (`release_segment_if_unused`): had a sibling port on the same network and
    physnet still been bound, the segment and its VLAN id would have to stay.
    This scenario sets up a single consumer so that the release is the correct
    outcome; `BM-BIND-REUSE-01` covers the sharing that makes the condition
    necessary.
- status: **KNOWN BUG (xfail, rackerlabs/understack#2239)** — the driver does not
  release the segment on detach today (see "Known bugs"). The test asserts the
  desired behavior and is marked `xfail(strict=True)`, so it will start failing
  (prompting removal of the xfail) once the bug is fixed.

### BM-BIND-05 — port delete releases the dynamic VLAN segment if unused
- given: a bound baremetal port (per BM-BIND-01), and it is the **only** port
  bound to that dynamic VLAN segment
- when: the port is deleted
- then: `undersync.sync(<physnet>)` reconciles the switch, and the dynamic VLAN
  segment is released **because, and only because, no ports remain bound to
  it**. Deleting a port is not by itself a reason to free the VLAN id: if any
  other port on the same `(network, physnet)` pair is still bound, the segment
  must survive the delete.

### BM-DEL-SHARED-01 — deleting one of two ports sharing a segment keeps it
- given: two baremetal ports on the same VXLAN network, both bound on
  `physnet1` and therefore sharing one dynamic VLAN segment (per
  BM-BIND-REUSE-01)
- when: the first port is deleted
- then: `undersync.sync(physnet1)` reconciles the switch but the dynamic VLAN
  segment is **retained** — the surviving port is still bound to it and still
  needs that VLAN on the switch. This is the negative half of BM-BIND-05: it
  pins down that the release is conditional rather than an unconditional
  consequence of deleting a port.

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
  allocation — both servers must land in the same broadcast domain on that
  switch pair, and the physnet's VLAN pool is finite. This shared segment is
  what makes the release in BM-BIND-04 / BM-BIND-05 necessarily conditional.

### PROV-BIND-01 — provisioning-network port binds
- given: a network configured as `ml2_understack.provisioning_network`
- when: a baremetal port on it is vif-attached
- then: it binds hierarchically and `undersync.sync(<physnet>)` fires (no special
  casing on the bind path)

### PROV-DEL-01 — provisioning-network port delete releases the VLAN segment if unused
- given: a bound baremetal port on the network configured as
  `ml2_understack.provisioning_network`
- when: the port is deleted
- then: the provisioning network behaves like any other network —
  `undersync.sync(<physnet>)` fires and the dynamic VLAN segment is released if
  no ports remain bound to it. While other nodes are still provisioning on the
  same VLAN group, their binding levels hold the segment open; once the last
  provisioning port goes away the VLAN id returns to the pool, and the next
  provision allocates again.
- note: the delete path used to return early for the provisioning network and
  skip the release entirely. There is no reason for it to be special here —
  `release_segment_if_unused` is already the safe, reference-counted operation,
  so the unconditional skip could only leak VLAN ids. The early return is gone;
  the `undersync.sync` that signals the end of the provisioning / cleaning cycle
  is the same call every other network gets.

## Trunk subport operations

A trunk lets one baremetal NIC carry several networks: the parent port's
network is the untagged/native VLAN on the switchport, and each **subport** is
an additional network carried as a tagged VLAN on the same switchport.

The subport's VLAN comes from the same `(network, physnet)` dynamic segment
machinery as a normal bound port, on the **parent's** physnet — the switch pair
the parent is cabled to is the one that has to carry the extra VLAN. A subport
never binds through the ML2 chain (nothing does a vif-attach for it), so the
trunk driver writes the level-0 `ml2_port_binding_levels` row itself
(`utils.create_binding_profile_level`, driver `understack`, level 0). That
synthetic row is what records "this subport's network is carried on VLAN *X* of
the parent's switchport", and it is also what keeps the shared segment
reference-counted: removing a subport deletes its row and then releases the
segment only if no rows are left pointing at it.

Note that a subport carries *two* VLAN ids that are easy to confuse: the
tenant-facing `segmentation_id` the user chose in the trunk API (what the
instance tags its frames with), and the fabric VLAN id of the dynamic segment on
the parent's physnet. The scenarios below are about the latter.

These scenarios load the real neutron trunk service plugin
(`UnderstackMl2TrunkScenarioBase`). The parent is a bound baremetal port; subport
adds/removes must reconcile the parent's switch (VLAN group).
`utils.fetch_network_node_trunk_id` (live OVN + Ironic discovery) is stubbed.

### TRUNK-SUB-ADD — subport attach syncs the parent's physnet
- given: a bound baremetal parent port on `physnet1` with a trunk, and a subport
  port on another network
- when: the subport is added to the trunk (VLAN segmentation)
- then:
  - the trunk records the subport
  - the trunk driver obtains the dynamic VLAN segment for the subport's network
    on the parent's physnet (`physnet1`), reusing an existing one for that
    `(network, physnet)` pair if there is one and allocating a new one
    otherwise
  - it writes a level-0 `ml2_port_binding_levels` row for the subport (driver
    `understack`, host = the parent's binding host) pointing at that segment —
    that row is the record that the subport's network is carried on this VLAN
    of the parent's switchport
  - `undersync.sync(physnet1)` reconciles the parent port's switch

### TRUNK-SUB-DEL — subport removal syncs the parent's physnet
- given: the TRUNK-SUB-ADD setup with the subport attached
- when: the subport is removed from the trunk
- then: the trunk result no longer contains the subport, its synthetic level-0
  binding row is deleted, the dynamic VLAN segment it pointed at is released
  **because that row was the last reference to it**, and
  `undersync.sync(physnet1)` reconciles the parent port's switch. Had another
  port or subport still been bound to that segment, only the row would go and
  the segment would stay.

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
- then: the trunk is gone, the subport's level-0 binding row is deleted and the
  dynamic segment released as no reference to it remains, the parent switchport
  is cleaned, and `undersync.sync(physnet1)` fires

### TRUNK-MULTI-01 — adding multiple subports syncs the parent's physnet
- given: a bound baremetal parent with a trunk
- when: two subports on different networks are added in one operation
- then: each subport gets its own level-0 binding row pointing at the dynamic
  VLAN segment for *its* network on `physnet1` — reusing the existing segment
  for that `(network, physnet)` pair if one is already in use, otherwise
  allocating a fresh one from the physnet's pool. Here the two subports are on
  different networks, so they end up on two distinct segments (two VLAN ids);
  two subports on the *same* network would share one. `undersync.sync(physnet1)`
  fires.

### TRUNK-PARENT-UNBOUND-01 — subport add with an unbound parent is a no-op
- given: an unbound (plain) parent port with a trunk
- when: a subport is added
- then: trunk membership is recorded, but no subport binding level row or
  dynamic VLAN segment is created and no `undersync.sync` occurs — with no
  parent binding there is no physnet to carry the subport on and nothing to
  reconcile

### TRUNK-SEGID-RANGE-01 — subport seg_id outside the allowed range is rejected
- given: a bound baremetal parent with a trunk
- when: a subport is added with a segmentation_id outside `[1, 3799]`
- then: `SubportSegmentationIDError` (raised in the SUBPORTS PRECOMMIT_CREATE
  callback, surfaced as `CallbackFailure`), with no binding level or dynamic
  segment allocated

### TRUNK-ORDER-01 — subport removal deallocates before it notifies Undersync
- given: a bound baremetal parent with a trunk and an attached subport
- when: the subport is removed
- then: on the shared SUBPORTS AFTER_DELETE event, the understack trunk driver's
  segment deallocation runs before the undersync driver's `sync`, since undersync
  reconciles from real device state and must not be told to reconcile until the
  segment work is done. The ordering comes from undersync subscribing at a
  priority above the understack trunk driver's `PRIORITY_DEFAULT`

## Router interface (VRF & SVI flavors)

These scenarios load a real L3 router + flavors plugin (`ML2TestFramework`). The
VRF and SVI flavored router paths skip the OVN uplink work, so no OVN IDL fake is
needed. The flavored path is simulated by patching `routers._router_has_flavor`
(and `svi._is_svi_router` for the SVI scenarios), mirroring the existing unit
tests.

The VRF and SVI flavors are close cousins: both realize the router as an SVI
(switched virtual interface) on the switching fabric. The difference is only
which VRF the SVI lands in — the VRF flavor first creates a dedicated VRF and
places the SVI into it, while the SVI flavor drops the SVI into a well-known VRF
that is part of the base switch configuration. So their scenarios are near
mirror images of each other.

### VRF-ROUTER-ATTACH-01 — VRF router attach syncs bound baremetal port physnets
- given: a VXLAN network + subnet with baremetal ports bound to two different
  physnets (`physnet1`, `physnet2`)
- when: a VRF router is created and the subnet is attached on the internal side
- then: undersync syncs each physnet carrying the network's baremetal ports so
  the switches are reconciled for the new router
- status: **KNOWN BUG (xfail, rackerlabs/understack#2240)** — attaching the VRF
  router interface does not sync those physnets today (`undersync.sync` is never
  called for them). The test asserts the desired behavior and is
  `xfail(strict=True)`.

### VRF-ROUTER-DETACH-01 — VRF router detach syncs bound baremetal port physnets
- given: a VXLAN network with baremetal ports on two physnets and an attached
  VRF router interface
- when: the router interface is removed
- then: undersync should sync each physnet still carrying baremetal ports
- status: **KNOWN BUG (xfail, rackerlabs/understack#2240)** — the teardown
  counterpart of VRF-ROUTER-ATTACH-01; detach does not sync those physnets today.

### SVI-ROUTER-ATTACH-01 — SVI router attach syncs bound baremetal port physnets
- given: a VXLAN network + an address-scoped IPv4 subnet, with baremetal ports
  bound to two different physnets (`physnet1`, `physnet2`)
- when: an SVI router is created and the subnet is attached on the internal side
- then: undersync syncs each physnet carrying the network's baremetal ports so
  the switches are reconciled for the new router
- status: **KNOWN BUG (xfail, rackerlabs/understack#2240)** — the same gap as
  VRF-ROUTER-ATTACH-01 for the SVI flavor: attaching the SVI router interface does not
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

A non-flavored router is realized by OVN, which runs on the **network nodes**,
not on the leaf switches. So when such a router gains an interface on a tenant
network, that network has to be extended from the fabric up to the network
nodes. That extension is the **uplink**: a dynamic VLAN segment on the network
nodes' physnet, a shared Neutron port named `uplink-<segment-id>` holding it, a
subport on the network-node trunk tagging that VLAN, and an OVN `localnet`
logical switch port on the network's logical switch carrying the same tag. One
uplink per network, built by the first router interface and torn down by the
last — hence OVN-ROUTER-SECOND-01 being a no-op.

These load an L3 router + flavors + trunk plugin
(`UnderstackMl2RouterOvnScenarioBase`) and patch `routers.ovn_client` with a
`FakeOvnClient` (records localnet LSP create/delete; short-circuits the vxlan
HCG workaround). `utils.fetch_network_node_trunk_id` is mocked to a trunk the
test creates.

### OVN-ROUTER-ATTACH-01 — non-flavored router attach builds the uplink
- given: a network+subnet, a network-node trunk, and a non-flavored router
- when: the subnet is attached on the internal side
- then: a VLAN uplink segment marked dynamic is allocated on the network-node
  physnet; the shared `uplink-` neutron port, trunk subport tag, and OVN localnet
  LSP tag all reference that segment and VLAN on the network's logical switch

### OVN-ROUTER-SECOND-01 — second router on the same network is a no-op
- given: a network with two subnets, the first already attached to a router
- when: a second router attaches the second subnet
- then: no new uplink is built (`is_only_router_port_on_network` is false)

### OVN-ROUTER-DETACH-01 — remove_router_interface tears down the uplink
- given: a network with a router interface and its uplink
- when: the interface is removed
- then: the shared port is removed from the network-node trunk, both the
  `uplink-<segment-id>` localnet LSP and shared-port LSP are deleted from the
  exact logical switch, the shared `uplink-` neutron port is removed, and the
  dynamic segment is released
- status: **KNOWN BUG (xfail, rackerlabs/understack#2245)** — teardown deletes
  the ports but leaks the dynamic uplink VLAN segment today. The test asserts
  the desired release and is `xfail(strict=True)`; a separate fix branch
  resolves it (flipping this to a pass once merged).

## Router flavor providers (Palo Alto)

These register the Palo Alto provider as an L3 service provider and create a real
flavor + service profile (`driver` = the PaloAlto class, `metainfo.resource_class`
= the netdev pool). `IronicClient` is faked (single-node pool).

### PALO-ROUTER-ADOPT-01 — Palo Alto router adopts an Ironic netdev node
- given: the Palo Alto provider registered and a matching flavor
- when: a router with that flavor is created
- then: the ROUTER BEFORE_CREATE callback requests a node using the service
  profile's resource class and adopts it with the router's project, ID, and name
  (via the faked Ironic client)

### PALO-ROUTER-RELEASE-01 — deleting a Palo Alto router releases its node
- given: a Palo Alto router that adopted a node
- when: the router is deleted
- then: the ROUTER AFTER_DELETE callback returns the node to the pool

## Current limitations and follow-up

- The Palo Alto external-gateway lifecycle landed on `main` after this scenario
  suite was started. Its parent-port creation, Ironic VIF attachment, trunk and
  gateway-subport wiring, idempotency, partial-failure cleanup, and detach/delete
  paths have focused unit coverage, but are not yet exercised through this
  in-process scenario harness. Add end-to-end attach and detach scenarios in a
  follow-up.
- Known-bug scenarios currently apply `xfail(strict=True)` to the whole test.
  This makes fixed behavior visible as an XPASS, but an unrelated failure in the
  same test could also be reported as the expected failure. A follow-up should
  constrain each xfail to the known failure signature (or make only the affected
  assertion an expected failure) so regressions elsewhere remain failures.

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
  unbound without being deleted. The fix is to pass the dynamic (bottom) segment
  to `release_segment_if_unused` on the detach transition — still conditional, so
  a segment shared with a sibling port on the same `(network, physnet)` pair is
  left alone. The xfail flips to a pass once fixed.

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

SVI validation:
- SVI-EXTGW-01 — an SVI router cannot get an external gateway. Needs the real
  Svi provider + flavor wiring (the `_reject_svi_external_gateway` callback),
  which the patched-flavor scenarios do not load.

Router (needs an OVN IDL fake for `routers.ovn_client()`):
- OVN-ROUTER-DELETE-01 — `delete_router` cleanup via `handle_router_interface_removal`
  (PORT PRECOMMIT_DELETE). Not reachable with the standard L3 plugin, which
  raises RouterInUse unless interfaces are removed first; needs a trigger that
  deletes a router-interface port directly.
- OVN-ROUTER-HCG-VXLAN-01 — `link_vxlan_network_ha_chassis_group` populates the unified
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
