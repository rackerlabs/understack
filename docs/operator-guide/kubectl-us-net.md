# kubectl-us-net

`kubectl-us-net` is a `kubectl` plugin for troubleshooting UnderStack's
Neutron/OVN data plane. It wraps `kubectl exec` into the OVN NB/SB pods
(and, for `ovs-vsctl`/`ovs-appctl`, whichever pod is running on a given
node) alongside OpenStack API calls, so you don't have to remember pod
names, container names, or the `neutron-<uuid>` naming convention OVN uses
for objects it syncs from Neutron.

It's a companion to the manual debugging steps in
[OVN / Open vSwitch](ovs-ovn.md) -- for example, the walkthrough in
[Verifying a router port is bound to an HA_Chassis_Group](ovs-ovn.md#verifying-a-router-port-is-bound-to-an-ha_chassis_group)
is exactly what `router show` (below) automates in one command.

This is intentionally a plain Python CLI for now (no compiled binary, no
krew packaging) so the command surface and output can be iterated on
quickly. Distributing it via krew is planned once the behavior settles.

## Installation

```bash
cd python/kubectl-us-net
uv sync
export PATH="$PWD/.venv/bin:$PATH"   # so `kubectl us-net ...` finds it
```

## Prerequisites

- `kubectl`, pointed at the target cluster (via `--context` or your current
  context)
- OpenStack credentials available on your machine -- `OS_CLOUD` env var /
  `clouds.yaml`, or pass `--os-cloud` explicitly

This tool doesn't manage either of those; it only reads them.

## Global options

| Option | Default | Description |
|---|---|---|
| `--context` | current kubectl context | kubectl context to target |
| `--namespace`, `-n` | `openstack` | Namespace hosting the OVN NB/SB pods |
| `--nb-pod` | `ovn-ovsdb-nb-0` | Northbound OVSDB pod name |
| `--sb-pod` | `ovn-ovsdb-sb-0` | Southbound OVSDB pod name |
| `--os-cloud` | `OS_CLOUD` env / clouds.yaml default | OpenStack cloud name |

Every command starts by printing a banner showing the kube context, OVN
namespace/pod names, and (for OpenStack-backed commands) the OpenStack cloud
target, so it's always clear what you're actually talking to.

## Commands

### Raw passthrough

```bash
kubectl us-net nbctl -- show
kubectl us-net sbctl -- list Chassis
kubectl us-net vsctl --node <nodename> -- show
kubectl us-net appctl --node <nodename> -- version
```

Thin wrappers around `ovn-nbctl`, `ovn-sbctl`, `ovs-vsctl`, and
`ovs-appctl` that resolve the right pod for you and stream native output
straight through -- use these for anything not covered by a higher-level
command below.

`vsctl`/`appctl` resolve the target pod by node name. On UnderStack's OVN
deployment, OVS is co-located inside the `ovn-controller` DaemonSet pod (no
separate `openvswitch` pod), so both commands default to the
`ovn-controller` name-prefix. If your cluster's pod naming differs, pass
`--pod <name>` (and, if needed, `--container <name>`) to target it
directly, or `--target <prefix>` on `appctl` to change the discovery
prefix.

### router list

```bash
kubectl us-net router list
```

A table of every router seen in OpenStack and/or OVN, so you can spot
mismatches (present on only one side) before drilling into one with
`router show`. Flavored routers (e.g. VRF) are handled by a different L3
backend and never get an OVN `Logical_Router`, so they're marked
`n/a (flavored)` in the OVN column rather than a false "NO".

```console
$ kubectl us-net router list
NAME             ID                                    OPENSTACK  OVN
---------------------------------------------------------------------
tenant-router    769be712-d084-4846-bd21-a85f6494f3b6  yes        yes
patch-router     94c6e0ee-3959-49e2-a9f2-e5f3a304bb77  yes        yes
vrf-router       df9746b3-d1da-484c-bf4c-86248279dddb  yes        n/a (flavored)
vrf-router-2     8f3492e8-d4d9-4f27-817c-b53a19b91f67  yes        n/a (flavored)
```

### router show

```bash
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
- Optionally, southbound logical flows (`ovn-sbctl lflow-list`), with
  `--flows`.

!!! note
    As of this writing, every router in UnderStack is **centralized** --
    there are no VLAN/FLAT distributed-gateway routers deployed, so the
    `Gateway_Chassis` path above is exercised only by unit tests, not live
    traffic. A router port should show up as **"Pinned chassis"**
    (`options:chassis`), not a router-port-level `HA_Chassis_Group`. The
    per-network `HA_Chassis_Group` is expected on **external ports bound to
    physical baremetal servers** instead (the `Ports` section below) -- that
    is a different, per-network HCG used to steer traffic to the chassis
    wired to that server's physical network, and is unrelated to router
    centralization. If a router port ever shows a linked HCG of its own, or
    a baremetal external port has none, treat it as a red flag worth
    investigating with `router show`'s "likely bug" diagnostics.

Example output (IPs and hostnames below are illustrative, not real):

```console
$ kubectl us-net --context my-cluster-dev --os-cloud example-cloud router show patch-router
================================================================
kubectl-us-net -- target environment
================================================================
  Kubernetes context : my-cluster-dev
  OVN namespace/pods : openstack (nb=ovn-ovsdb-nb-0, sb=ovn-ovsdb-sb-0)
  OpenStack cloud    : example-cloud
    auth URL         : https://keystone.dev.undercloud.example.com/v3
    project          : baremetal
================================================================


Router patch-router (94c6e0ee-3959-49e2-a9f2-e5f3a304bb77)
OVN Logical_Router: neutron-94c6e0ee-3959-49e2-a9f2-e5f3a304bb77
Type: centralized (options:chassis=a2172b59-5558-4018-858d-88947e2d9adf)

Router ports:
  - lrp-6aeee225-e410-4a7a-891d-edc2a3f3831f [gateway]
      Neutron port      : 6aeee225-e410-4a7a-891d-edc2a3f3831f
      OVN networks      : 203.0.113.41/26
      Neutron fixed IPs : 203.0.113.41
      Network VLAN tag  : 1804, 1800
      Pinned chassis    : a2172b59-5558-4018-858d-88947e2d9adf (alive, physnets=physnet1)
  - lrp-c0a41495-4cb5-4913-a7e7-9a2047f79e7d [internal]
      Neutron port      : c0a41495-4cb5-4913-a7e7-9a2047f79e7d
      OVN networks      : 192.0.2.1/24
      Neutron fixed IPs : 192.0.2.1
      Network VLAN tag  : 1802
      Pinned chassis    : a2172b59-5558-4018-858d-88947e2d9adf (alive, physnets=physnet1)

NAT rules:
  dnat_and_snat  external=203.0.113.19   logical=192.0.2.156  -> port d0075095-6232-43a6-b0c0-7fd7a07716a3
  snat           external=203.0.113.41   logical=192.0.2.0/24

Ports:
  d0075095-6232-43a6-b0c0-7fd7a07716a3 ((unnamed))
      Fixed IPs        : 192.0.2.156
      Owner            : server 14d4e13f-fef5-4676-a8e2-a5bdf63c2b6f (web-server-01)
      OVN LSP          : type=external, up, addresses=d4:04:e6:4f:7e:cc 192.0.2.156
      HA_Chassis_Group : neutron-5af67e57-7052-49fc-9bad-253275b39986 -> a2172b59-5558-4018-858d-88947e2d9adf (priority=32767, alive, physnets=physnet1)
```

Here the router port shows a **pinned chassis** (expected for a centralized
router), while the baremetal server's external port shows its own
**`HA_Chassis_Group`** -- exactly the split described in the note above.

## Development

Each command is a self-contained module under `us_net/commands/` that
registers into the top-level `typer` app (`us_net/cli.py`). Low-level OVSDB
access lives in `us_net/ovn.py` (JSON unwrap ported from
`scripts/cleanup_dead_ovn_ha_chassis.py`), `kubectl exec` plumbing in
`us_net/kube.py`, and OpenStack SDK connection setup in
`us_net/osclient.py`. Run tests and linting from `python/kubectl-us-net/`:

```bash
uv run pytest
uv run ruff check
uv run ruff format
```

## Contributing

If you find any issues or have suggestions for improvements, please open an
issue on the [GitHub repository](https://github.com/rackerlabs/understack).
