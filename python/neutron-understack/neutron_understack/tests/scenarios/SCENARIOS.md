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
