# kubectl-us-net

A `kubectl` plugin for troubleshooting UnderStack's Neutron/OVN data plane.
Wraps `kubectl exec` into the OVN NB/SB pods (and, for `ovs-vsctl`/`ovs-appctl`,
whichever pod is running on a given node) alongside OpenStack API calls, so
you don't have to remember pod names, container names, or the
`neutron-<uuid>` naming convention OVN uses for objects it syncs from
Neutron.

This is intentionally a plain Python CLI for now (no compiled binary, no
krew packaging) so the command surface and output can be iterated on
quickly. Distributing it via krew is planned once the behavior settles.

## Setup

```
cd python/kubectl-us-net
uv sync
export PATH="$PWD/.venv/bin:$PATH"   # so `kubectl us-net ...` finds it
```

Requires `kubectl` (pointed at the target cluster) and OpenStack credentials
(`OS_CLOUD` env var / `clouds.yaml`, or pass `--os-cloud` explicitly) already
available on your machine -- this tool doesn't manage either.

## Usage

Every command starts by printing a banner showing the kube context, OVN
namespace/pod names, and (for OpenStack-backed commands) the OpenStack cloud
target -- so it's always clear what you're actually talking to.

### Raw passthrough

```
kubectl us-net nbctl -- show
kubectl us-net sbctl -- list Chassis
kubectl us-net vsctl --node <nodename> -- show
kubectl us-net appctl --node <nodename> -- version
```

`vsctl`/`appctl` resolve the target pod by node name. On UnderStack's OVN
deployment, OVS is co-located inside the `ovn-controller` DaemonSet pod (no
separate `openvswitch` pod), so both commands default to the
`ovn-controller` name-prefix. If your cluster's pod naming differs, pass
`--pod <name>` (and, if needed, `--container <name>`) to target it directly,
or `--target <prefix>` on `appctl` to change the discovery prefix.

### `router list`

```
kubectl us-net router list
```

A table of every router seen in OpenStack and/or OVN, so you can spot
mismatches (present on only one side) before drilling into one with
`router show`. Flavored routers (e.g. VRF) are handled by a different L3
backend and never get an OVN `Logical_Router`, so they're marked
`n/a (flavored)` in the OVN column rather than a false "NO".

### `router show`

```
kubectl us-net router show <router-name-or-id>
kubectl us-net router show <router-name-or-id> --flows   # also dump SB logical flows
```

Resolves the router in OpenStack, maps it to its OVN `Logical_Router`
(`neutron-<router_id>`), and prints:

- **Router ports** -- each `Logical_Router_Port` (gateway vs. internal), its
  Neutron port ID, OVN-side networks and Neutron-side fixed IPs, the VLAN
  tag(s) of its network's localnet/uplink port(s), and its chassis binding:
  - a linked `HA_Chassis_Group`, with each chassis's liveness and physical
    networks (via `ovn-bridge-mappings`), highest priority first;
  - or, for a VLAN/FLAT distributed gateway, its `Gateway_Chassis` binding
    (OVN's own L3-scheduler mechanism, distinct from `ha_chassis_group`);
  - or, for a centralized router, the chassis it's pinned to via
    `options:chassis`;
  - and only flags a port as "likely bug" when *none* of the above apply --
    the exact bug class `scripts/cleanup_dead_ovn_ha_chassis.py` repairs.
- **NAT rules** -- each rule's type/external IP/logical IP, and the
  OpenStack port it resolves to (if any).
- **Ports** -- for each NAT-resolved port: its fixed IPs, owner (server name
  for compute-owned ports), a cross-check against its OVN `Logical_Switch_Port`
  (type/up/addresses), and that port's own `HA_Chassis_Group` binding (the
  per-network unified HCG referenced by external/baremetal ports, distinct
  from the router-port-level HCG shown above).
- Optionally, southbound logical flows (`ovn-sbctl lflow-list`).

### `router audit`

```
kubectl us-net router audit <router-name-or-id>
```

Checks native OVN routers for their logical router, LRP/LSP attachments,
router peer LSP type, addresses, required options, and `requested-chassis`
membership with `binding:host_id`. Gateway LSPs must use the network logical
switch. Router interfaces use it today; a segment-stamped interface is also
accepted on its segment switch as a defensive forward-compatibility path.
Attached LRPs and peer LSPs without a Neutron router port are reported as
orphans.
For each router network, the audit also verifies that its single shared
Neutron `uplink-*` port has a matching `localnet` LSP on the network logical
switch with `addresses=unknown` and exactly one VLAN tag.
Router-owned per-network `HA_Chassis_Group` rows are also checked for at least
one member backed by a live Southbound chassis. An empty or stale-only group is
reported as requiring per-network HA chassis group repopulation, along with
whether the router has an unambiguous live chassis from which to repair it.
Flavored routers are skipped because their realization is outside this
command's scope. Any failed check produces a nonzero exit status.

### `router repair`

```
kubectl us-net router repair <router-name-or-id>          # dry-run plan
kubectl us-net router repair <router-name-or-id> --apply  # write and verify
```

Narrowly repairs the `type`, `addresses`, `router-port`, and gateway-only
`nat-addresses`/`exclude-lb-vips-from-garp` fields of existing, correctly
attached native-OVN peer LSPs. Map keys are updated individually, so unrelated
options such as `requested-chassis` are preserved.
Shared `uplink-*` localnet LSPs are audit-only and are not recreated by this
command.

The same transaction repopulates a router-owned per-network HA chassis group
when it has no live members. The target must be unambiguous: a live
`Logical_Router.options:chassis`, or, for a distributed router, exactly one
live chassis resolved through the router's own HA chassis group. Stale member
references are removed from the affected per-network group, a replacement is
created at priority `32767`, and the result is read back for verification.
Verification checks that the selected chassis was added at that priority and
that every stale member reference in the plan was removed.

Repair refuses flavored routers, missing objects, wrong attachments, attached
LRPs without Neutron router ports, and HA chassis placement that is unavailable
or ambiguous. LSP and HA chassis group repairs are independent: a refusal in
one does not block safe changes in the other, but a partial repair exits `2`.
For fleet-wide stale-member cleanup and group repopulation, see
[`cleanup_dead_ovn_ha_chassis.py`](../../scripts/cleanup_dead_ovn_ha_chassis.py).
See the
[operator guide](../../docs/operator-guide/kubectl-us-net.md#router-repair) for
the complete safety contract.

## Global options

- `--context` -- kubectl context (default: current context)
- `--namespace` / `-n` -- namespace hosting the OVN NB/SB pods (default: `openstack`)
- `--nb-pod` / `--sb-pod` -- NB/SB pod names (default: `ovn-ovsdb-nb-0` / `ovn-ovsdb-sb-0`)
- `--os-cloud` -- OpenStack cloud name (default: `OS_CLOUD` env / clouds.yaml default)
