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

## Global options

- `--context` -- kubectl context (default: current context)
- `--namespace` / `-n` -- namespace hosting the OVN NB/SB pods (default: `openstack`)
- `--nb-pod` / `--sb-pod` -- NB/SB pod names (default: `ovn-ovsdb-nb-0` / `ovn-ovsdb-sb-0`)
- `--os-cloud` -- OpenStack cloud name (default: `OS_CLOUD` env / clouds.yaml default)
