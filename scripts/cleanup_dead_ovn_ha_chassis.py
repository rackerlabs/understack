#!/usr/bin/env python3
"""Repair OVN HA_Chassis_Group state left behind by chassis decommissioning.

Three related problems (phase 3 is opt-in, see --delete-orphaned-networks):

1. Stale HA_Chassis rows. An HA_Chassis row is "dead" when its chassis_name
   does not match any currently-registered chassis in the Southbound DB —
   typically left behind after a host is decommissioned/replaced. Dead rows
   sitting in an HA_Chassis_Group don't just waste space:
   neutron_understack's link_vxlan_network_ha_chassis_group() (routers.py)
   requires every HA_Chassis row in the whole NB database to share a single
   chassis_name before it will populate a network's unified
   HA_Chassis_Group. A single stale row anywhere breaks that check for
   every vxlan network in the fleet.

2. Empty per-network unified HA_Chassis_Groups. Once (1) has happened (or
   for any other reason a network's unified group ended up empty), its
   external/baremetal ports have no chassis to claim them. Normally you'd
   fix this per-router by detaching/reattaching a subnet to re-fire
   link_vxlan_network_ha_chassis_group. This script instead derives the
   right chassis directly from the router's own HA_Chassis_Group and writes
   it to the network's group (plus anchors the internal router-interface
   LRP to it), mirroring what that function does — for every affected
   network in one run, no manual per-router action needed.

3. Leftover networks from a half-deleted network. When a neutron network is
   deleted but OVN is left with a stale Logical_Switch (neutron-<network_id>),
   its ports, and its per-network HA_Chassis_Group, a subsequent
   neutron_ovn_db_sync_util run fails trying to delete the HCG because an
   external/baremetal Logical_Switch_Port still references it:
     "cannot delete HA_Chassis_Group row ... because of N remaining
      reference(s): referential integrity violation"
   Phase 3 tears the whole leftover network down (Logical_Switch + all its
   ports + the HCG, clearing any router-port references first) so the sync can
   proceed. It is opt-in (--delete-orphaned-networks) and DESTRUCTIVE, so it
   determines "orphaned" authoritatively by asking neutron itself
   (`openstack network list` / `network show`): a switch is only removed when
   its backing network is genuinely gone from neutron. A live network whose
   HCG the sync merely wants to reshape (e.g. a real baremetal port still
   present) is reported and skipped, never deleted.

Runs in dry-run mode by default. Pass --execute to apply changes.

Caveat: repopulation here is a direct, minimal OVN write. It does not
replicate neutron's candidate filtering (chassis-as-gw eligibility, physnet
connectivity, priority ordering across multiple chassis) that
sync_ha_chassis_group_network_unified performs. It only picks a chassis
if the router's own HA_Chassis_Group resolves to exactly one distinct live
chassis. This is safe for the common single-gateway-chassis case; in a
multi-chassis HA setup, prefer re-triggering the real neutron code path.
"""

import argparse
import json
import logging
import os
import subprocess
import sys

NB_POD = "ovn-ovsdb-nb-0"
SB_POD = "ovn-ovsdb-sb-0"
OVN_NAMESPACE = "openstack"

OVN_NETWORK_ID_EXT_ID_KEY = "neutron:network_id"
OVN_ROUTER_ID_EXT_ID_KEY = "neutron:router_id"
HA_CHASSIS_GROUP_HIGHEST_PRIORITY = 32767

log = logging.getLogger(__name__)


def _unwrap_ovn_value(val):
    """Recursively unwrap an OVN JSON-encoded value."""
    if not isinstance(val, list) or len(val) < 2:
        return val
    tag = val[0]
    if tag == "uuid":
        return val[1]
    if tag == "set":
        return [_unwrap_ovn_value(v) for v in val[1]]
    if tag == "map":
        return {_unwrap_ovn_value(k): _unwrap_ovn_value(v) for k, v in val[1]}
    return val


def parse_ovn_json(raw: str) -> list[dict]:
    """Parse OVN --format=json list output into a list of row dicts."""
    obj = json.loads(raw)
    headings = obj["headings"]
    return [
        {h: _unwrap_ovn_value(v) for h, v in zip(headings, row)} for row in obj["data"]
    ]


def _as_list(val) -> list:
    """OVSDB unwraps single-element sets to a bare value instead of a list."""
    if val in (None, ""):
        return []
    return val if isinstance(val, list) else [val]


def _ovn_cmd(
    kubectl_base: list[str], pod: str, ctl: str, *args: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        kubectl_base + ["exec", "-n", OVN_NAMESPACE, pod, "--", ctl] + list(args),
        capture_output=True,
        text=True,
    )


def _ovn_list(
    kubectl_base: list[str], pod: str, ctl: str, table: str, columns: str
) -> list[dict]:
    result = _ovn_cmd(
        kubectl_base, pod, ctl, f"--columns={columns}", "--format=json", "list", table
    )
    if result.returncode != 0:
        print(
            f"ERROR: {ctl} list {table} failed:\n{result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    return parse_ovn_json(result.stdout)


def get_live_chassis_names(kubectl_base: list[str]) -> set[str]:
    """Chassis names currently registered in the Southbound DB."""
    rows = _ovn_list(kubectl_base, SB_POD, "ovn-sbctl", "Chassis", "name")
    return {r["name"] for r in rows}


def get_all_ha_chassis(kubectl_base: list[str]) -> list[dict]:
    """Every HA_Chassis row in the Northbound DB."""
    return _ovn_list(
        kubectl_base, NB_POD, "ovn-nbctl", "HA_Chassis", "_uuid,chassis_name,priority"
    )


def get_all_ha_chassis_groups(kubectl_base: list[str]) -> list[dict]:
    """Every HA_Chassis_Group row in the Northbound DB."""
    return _ovn_list(
        kubectl_base,
        NB_POD,
        "ovn-nbctl",
        "HA_Chassis_Group",
        "_uuid,name,ha_chassis,external_ids",
    )


def get_all_router_ports(kubectl_base: list[str]) -> list[dict]:
    """Every Logical_Router_Port row in the Northbound DB."""
    return _ovn_list(
        kubectl_base, NB_POD, "ovn-nbctl", "Logical_Router_Port", "name,external_ids"
    )


# --- Phase 1: stale HA_Chassis cleanup -------------------------------------


def find_stale_ha_chassis(
    all_ha_chassis: list[dict], live_chassis: set[str]
) -> list[dict]:
    """Return HA_Chassis rows whose chassis_name isn't a currently-live chassis."""
    stale = [r for r in all_ha_chassis if r["chassis_name"] not in live_chassis]
    for r in stale:
        log.debug(
            "Stale HA_Chassis %s chassis_name=%s priority=%s",
            r["_uuid"],
            r["chassis_name"],
            r["priority"],
        )
    return stale


def map_groups_to_stale_members(
    groups: list[dict], stale_uuids: set[str]
) -> list[dict]:
    """Return one record per (group, stale member) pair, plus resulting size."""
    records = []
    for g in groups:
        members = _as_list(g.get("ha_chassis"))
        stale_members = [m for m in members if m in stale_uuids]
        if not stale_members:
            continue
        for member_uuid in stale_members:
            records.append(
                {
                    "group_uuid": g["_uuid"],
                    "group_name": g["name"],
                    "member_uuid": member_uuid,
                    "remaining_after": len(members) - len(stale_members),
                }
            )
    return records


def print_cleanup_report(records: list[dict], stale_by_uuid: dict[str, dict]) -> None:
    print("=== Phase 1: stale HA_Chassis cleanup ===\n")
    if not records:
        print("[DRY-RUN] No stale HA_Chassis rows found. Nothing to clean up.\n")
        return

    print(f"[DRY-RUN] Found {len(records)} stale HA_Chassis reference(s):\n")
    for r in records:
        chassis_name = stale_by_uuid[r["member_uuid"]]["chassis_name"]
        print(f"[DRY-RUN]   Group  : {r['group_name']} ({r['group_uuid']})")
        print(f"[DRY-RUN]   Member : {r['member_uuid']} (dead chassis {chassis_name})")
        print(
            f"[DRY-RUN]   Action : ovn-nbctl remove HA_Chassis_Group "
            f"{r['group_uuid']} ha_chassis {r['member_uuid']}"
        )
        print()


def execute_cleanup(
    records: list[dict], kubectl_base: list[str], assume_yes: bool
) -> None:
    print("=== Phase 1: stale HA_Chassis cleanup ===\n")
    if not records:
        print("No stale HA_Chassis rows found. Nothing to do.\n")
        return

    print(f"About to remove {len(records)} stale HA_Chassis reference(s):")
    for r in records:
        print(
            f"  - HA_Chassis_Group {r['group_name']} ({r['group_uuid']}): "
            f"remove ha_chassis {r['member_uuid']}"
        )
    if not _confirm("Apply these Phase 1 changes?", assume_yes):
        print("Skipped Phase 1 — no changes made.\n")
        return

    args: list[str] = []
    for r in records:
        args += [
            "--",
            "remove",
            "HA_Chassis_Group",
            r["group_uuid"],
            "ha_chassis",
            r["member_uuid"],
        ]

    print(f"Removing {len(records)} stale HA_Chassis reference(s) in one transaction …")
    result = _ovn_cmd(kubectl_base, NB_POD, "ovn-nbctl", *args)
    if result.returncode != 0:
        log.error("Cleanup transaction failed: %s", result.stderr.strip())
        sys.exit(1)
    print("Done.\n")


# --- Phase 2: repopulate empty per-network unified HA_Chassis_Groups -------


def plan_repopulation(
    groups: list[dict],
    all_ha_chassis_by_uuid: dict[str, str],
    stale_uuids: set[str],
    router_ports: list[dict],
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Work out which empty per-network HCGs can be safely repopulated.

    A group is a candidate if: it's a per-network unified HCG (has
    neutron:network_id in external_ids), it has no members once stale ones
    are excluded, and its associated router's own HCG resolves to exactly
    one distinct live chassis.
    """
    groups_by_name = {g["name"]: g for g in groups}

    lrps_by_network: dict[str, list[dict]] = {}
    for lrp in router_ports:
        ext = lrp.get("external_ids") or {}
        net_name = ext.get("neutron:network_name")
        if net_name:
            lrps_by_network.setdefault(net_name, []).append(lrp)

    plan = []
    skipped = []
    for g in groups:
        ext = g.get("external_ids") or {}
        network_id = ext.get(OVN_NETWORK_ID_EXT_ID_KEY)
        if not network_id:
            continue  # not a per-network unified HCG (e.g. a per-router one)

        members = _as_list(g.get("ha_chassis"))
        remaining = [m for m in members if m not in stale_uuids]
        if remaining:
            continue  # already has (or will keep) a valid member

        router_id = ext.get(OVN_ROUTER_ID_EXT_ID_KEY)
        if not router_id:
            skipped.append((g["name"], "no router_id in HCG external_ids"))
            continue

        router_group = groups_by_name.get(f"neutron-{router_id}")
        if not router_group:
            skipped.append((g["name"], f"router HCG neutron-{router_id} not found"))
            continue

        router_members = _as_list(router_group.get("ha_chassis"))
        router_remaining = [m for m in router_members if m not in stale_uuids]
        chassis_names = {
            all_ha_chassis_by_uuid[m]
            for m in router_remaining
            if m in all_ha_chassis_by_uuid
        }
        if len(chassis_names) != 1:
            skipped.append(
                (
                    g["name"],
                    f"router HCG resolves to {len(chassis_names)} distinct "
                    "live chassis (expected exactly 1)",
                )
            )
            continue
        target_chassis = next(iter(chassis_names))

        switch_name = f"neutron-{network_id}"
        candidates = [
            lrp
            for lrp in lrps_by_network.get(switch_name, [])
            if (lrp.get("external_ids") or {}).get("neutron:router_name")
            == f"neutron-{router_id}"
        ]
        if not candidates:
            skipped.append(
                (
                    g["name"],
                    f"no internal Logical_Router_Port found for network "
                    f"{network_id} on router {router_id}",
                )
            )
            continue
        if len(candidates) > 1:
            log.warning(
                "Multiple internal LRPs found for network %s on router %s; using %s",
                network_id,
                router_id,
                candidates[0]["name"],
            )

        plan.append(
            {
                "group_uuid": g["_uuid"],
                "group_name": g["name"],
                "network_id": network_id,
                "router_id": router_id,
                "target_chassis": target_chassis,
                "lrp_name": candidates[0]["name"],
            }
        )
    return plan, skipped


def print_repopulation_report(plan: list[dict], skipped: list[tuple[str, str]]) -> None:
    print("=== Phase 2: repopulate empty per-network HCGs ===\n")
    if not plan and not skipped:
        print("[DRY-RUN] No empty per-network HCGs found.\n")
        return

    for p in plan:
        print(f"[DRY-RUN]   Network HCG : {p['group_name']}")
        print(f"[DRY-RUN]   Router      : {p['router_id']}")
        print(f"[DRY-RUN]   Chassis     : {p['target_chassis']}")
        print(f"[DRY-RUN]   Anchor LRP  : {p['lrp_name']}")
        print(
            f"[DRY-RUN]   Action      : create HA_Chassis "
            f"chassis_name={p['target_chassis']} "
            f"priority={HA_CHASSIS_GROUP_HIGHEST_PRIORITY}; add to "
            f"{p['group_uuid']}; set {p['lrp_name']} "
            f"ha_chassis_group={p['group_uuid']}"
        )
        print()

    for name, reason in skipped:
        print(f"[DRY-RUN]   SKIPPED {name}: {reason}\n")


def execute_repopulation(
    plan: list[dict], kubectl_base: list[str], assume_yes: bool
) -> None:
    print("=== Phase 2: repopulate empty per-network HCGs ===\n")
    if not plan:
        print("No empty per-network HCGs to repopulate.\n")
        return

    print(f"About to repopulate {len(plan)} network HCG(s):")
    for p in plan:
        print(
            f"  - {p['group_name']}: chassis {p['target_chassis']}, "
            f"anchor LRP {p['lrp_name']}"
        )
    if not _confirm("Apply these Phase 2 changes?", assume_yes):
        print("Skipped Phase 2 — no changes made.\n")
        return

    args: list[str] = []
    for i, p in enumerate(plan):
        hc_id = f"@hc{i}"
        args += [
            "--",
            f"--id={hc_id}",
            "create",
            "HA_Chassis",
            f"chassis_name={p['target_chassis']}",
            f"priority={HA_CHASSIS_GROUP_HIGHEST_PRIORITY}",
            "--",
            "add",
            "HA_Chassis_Group",
            p["group_uuid"],
            "ha_chassis",
            hc_id,
            "--",
            "set",
            "Logical_Router_Port",
            p["lrp_name"],
            f"ha_chassis_group={p['group_uuid']}",
        ]

    print(f"Repopulating {len(plan)} network HCG(s) in one transaction …")
    result = _ovn_cmd(kubectl_base, NB_POD, "ovn-nbctl", *args)
    if result.returncode != 0:
        log.error("Repopulation transaction failed: %s", result.stderr.strip())
        sys.exit(1)
    print("Done.")
    for p in plan:
        print(f"  - {p['group_name']} -> {p['target_chassis']}")


# --- Phase 3: delete truly-orphaned leftover networks ---------------------

NEUTRON_PREFIX = "neutron-"

# Safety tripwire: if more than this fraction of OVN networks look orphaned,
# the OpenStack credentials almost certainly aren't admin (or can't list every
# network) rather than the fleet being mostly dead. Abort unless --force.
ORPHAN_SAFETY_FRACTION = 0.5


def _openstack_cmd(os_cloud: str | None, *args: str) -> subprocess.CompletedProcess:
    cmd = ["openstack"]
    if os_cloud:
        cmd += ["--os-cloud", os_cloud]
    return subprocess.run(cmd + list(args), capture_output=True, text=True)


def get_live_neutron_network_ids(os_cloud: str | None) -> set[str]:
    """Set of network IDs currently known to neutron (the authoritative source)."""
    result = _openstack_cmd(os_cloud, "network", "list", "-f", "value", "-c", "ID")
    if result.returncode != 0:
        print(
            "ERROR: `openstack network list` failed. Phase 3 needs working "
            "(admin) OpenStack credentials to tell live networks from orphaned "
            f"ones:\n{result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    ids = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    if not ids:
        print(
            "ERROR: `openstack network list` returned no networks. Refusing to "
            "treat every OVN network as orphaned — check your credentials.",
            file=sys.stderr,
        )
        sys.exit(1)
    return ids


def neutron_network_exists(network_id: str, os_cloud: str | None) -> bool | None:
    """Authoritatively check a single network: True/False, or None if unclear."""
    result = _openstack_cmd(
        os_cloud, "network", "show", network_id, "-f", "value", "-c", "id"
    )
    if result.returncode == 0:
        return True
    stderr = result.stderr.lower()
    not_found_markers = (
        "no network found",  # openstackclient: "No Network found for <id>"
        "network not found",
        "could not be found",
        "no network with a name or id",
    )
    if any(marker in stderr for marker in not_found_markers):
        return False
    log.warning(
        "Ambiguous `openstack network show %s` result; treating as unknown: %s",
        network_id,
        result.stderr.strip(),
    )
    return None


def get_all_logical_switches(kubectl_base: list[str]) -> list[dict]:
    """Every Logical_Switch row in the Northbound DB."""
    return _ovn_list(
        kubectl_base, NB_POD, "ovn-nbctl", "Logical_Switch", "_uuid,name,ports"
    )


def get_lsp_hcg_refs(kubectl_base: list[str]) -> list[dict]:
    """Every Logical_Switch_Port with its ha_chassis_group reference."""
    return _ovn_list(
        kubectl_base,
        NB_POD,
        "ovn-nbctl",
        "Logical_Switch_Port",
        "_uuid,name,ha_chassis_group",
    )


def get_lrp_hcg_refs(kubectl_base: list[str]) -> list[dict]:
    """Every Logical_Router_Port with its ha_chassis_group reference."""
    return _ovn_list(
        kubectl_base,
        NB_POD,
        "ovn-nbctl",
        "Logical_Router_Port",
        "_uuid,name,ha_chassis_group",
    )


def build_hcg_ref_map(rows: list[dict]) -> dict[str, list[dict]]:
    """Map HA_Chassis_Group uuid -> rows whose ha_chassis_group points at it."""
    refs: dict[str, list[dict]] = {}
    for r in rows:
        for hcg_uuid in _as_list(r.get("ha_chassis_group")):
            refs.setdefault(hcg_uuid, []).append(r)
    return refs


def plan_orphan_cleanup(
    switches: list[dict],
    hcg_by_name: dict[str, dict],
    lsp_refs: dict[str, list[dict]],
    lrp_refs: dict[str, list[dict]],
    os_cloud: str | None,
    force: bool,
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Work out which leftover networks are safe to tear down.

    A Logical_Switch (neutron-<network_id>) is orphaned only when neutron no
    longer has that network. We first diff against `openstack network list` to
    find suspects cheaply, then re-confirm each one with `openstack network
    show` before it is allowed into the deletion plan.
    """
    live_networks = get_live_neutron_network_ids(os_cloud)

    # LSP uuid -> owning switch name, so we can be sure an HCG's remaining
    # references all belong to the switch we're about to delete.
    switch_of_lsp: dict[str, str] = {}
    net_switches: list[dict] = []
    for s in switches:
        if not s["name"].startswith(NEUTRON_PREFIX):
            continue
        net_switches.append(s)
        for lsp_uuid in _as_list(s.get("ports")):
            switch_of_lsp[lsp_uuid] = s["name"]

    candidates = [
        s
        for s in net_switches
        if s["name"].removeprefix(NEUTRON_PREFIX) not in live_networks
    ]

    if (
        net_switches
        and len(candidates) / len(net_switches) > ORPHAN_SAFETY_FRACTION
        and not force
    ):
        print(
            f"ERROR: {len(candidates)} of {len(net_switches)} OVN networks look "
            f"orphaned (> {int(ORPHAN_SAFETY_FRACTION * 100)}%). That usually "
            "means the OpenStack credentials aren't admin or don't list every "
            "network, not that the fleet is mostly dead. Aborting Phase 3. "
            "Re-run with --force only if you are certain.",
            file=sys.stderr,
        )
        sys.exit(1)

    plan: list[dict] = []
    skipped: list[tuple[str, str]] = []
    for s in candidates:
        switch_name = s["name"]
        network_id = switch_name.removeprefix(NEUTRON_PREFIX)

        # Belt-and-suspenders: directly confirm this specific network is gone
        # before deleting anything, in case the list above was scoped/stale.
        exists = neutron_network_exists(network_id, os_cloud)
        if exists is True:
            skipped.append((switch_name, "neutron still has this network (live)"))
            continue
        if exists is None:
            skipped.append((switch_name, "could not confirm network is gone; skipping"))
            continue

        hcg = hcg_by_name.get(switch_name)
        hcg_uuid = hcg["_uuid"] if hcg else None

        # Every LSP referencing this HCG must live on the switch we're deleting.
        # A reference from a port on a different (possibly live) switch means the
        # topology isn't what we expect — skip rather than risk collateral damage.
        ref_lsps = lsp_refs.get(hcg_uuid, []) if hcg_uuid else []
        foreign = [
            lsp for lsp in ref_lsps if switch_of_lsp.get(lsp["_uuid"]) != switch_name
        ]
        if foreign:
            others = ", ".join(
                sorted(
                    switch_of_lsp.get(lsp["_uuid"], "<orphan LSP>") for lsp in foreign
                )
            )
            skipped.append(
                (
                    switch_name,
                    f"HCG also referenced by LSP(s) on other switch(es): {others}",
                )
            )
            continue

        ref_lrps = lrp_refs.get(hcg_uuid, []) if hcg_uuid else []
        plan.append(
            {
                "switch_name": switch_name,
                "network_id": network_id,
                "hcg_uuid": hcg_uuid,
                "hcg_name": hcg["name"] if hcg else None,
                "port_count": len(_as_list(s.get("ports"))),
                # LSPs on this switch that strongly reference the HCG. Their
                # reference must be cleared *explicitly* before the HCG can be
                # destroyed — relying on ls-del to GC the ports does not drop
                # the reference in time for the referential-integrity check.
                "ref_lsps": [
                    {"uuid": lsp["_uuid"], "name": lsp["name"]} for lsp in ref_lsps
                ],
                "ref_lrps": [
                    {"uuid": lrp["_uuid"], "name": lrp["name"]} for lrp in ref_lrps
                ],
            }
        )
    return plan, skipped


def _orphan_actions(p: dict) -> list[str]:
    actions = [
        f"clear Logical_Switch_Port {lsp['uuid']} ha_chassis_group"
        for lsp in p["ref_lsps"]
    ]
    actions += [
        f"clear Logical_Router_Port {lrp['uuid']} ha_chassis_group"
        for lrp in p["ref_lrps"]
    ]
    actions.append(f"ls-del {p['switch_name']} (deletes switch + all ports)")
    if p["hcg_uuid"]:
        actions.append(f"destroy HA_Chassis_Group {p['hcg_uuid']}")
    return actions


def _orphan_txn_args(p: dict) -> list[str]:
    """ovn-nbctl `--`-separated args to tear down one orphaned network."""
    args: list[str] = []
    for lsp in p["ref_lsps"]:
        args += [
            "--",
            "--if-exists",
            "clear",
            "Logical_Switch_Port",
            lsp["uuid"],
            "ha_chassis_group",
        ]
    for lrp in p["ref_lrps"]:
        args += [
            "--",
            "--if-exists",
            "clear",
            "Logical_Router_Port",
            lrp["uuid"],
            "ha_chassis_group",
        ]
    args += ["--", "--if-exists", "ls-del", p["switch_name"]]
    if p["hcg_uuid"]:
        args += ["--", "--if-exists", "destroy", "HA_Chassis_Group", p["hcg_uuid"]]
    return args


def print_orphan_report(plan: list[dict], skipped: list[tuple[str, str]]) -> None:
    print("=== Phase 3: delete truly-orphaned leftover networks ===\n")
    if not plan and not skipped:
        print("[DRY-RUN] No orphaned leftover networks found.\n")
        return

    for p in plan:
        print(f"[DRY-RUN]   Network : {p['network_id']} (gone from neutron)")
        print(f"[DRY-RUN]   Switch  : {p['switch_name']} ({p['port_count']} port(s))")
        if p["hcg_uuid"]:
            print(f"[DRY-RUN]   HCG     : {p['hcg_name']} ({p['hcg_uuid']})")
        print(f"[DRY-RUN]   Action  : {'; '.join(_orphan_actions(p))}")
        print()

    for name, reason in skipped:
        print(f"[DRY-RUN]   SKIPPED {name}: {reason}\n")


def execute_orphan_cleanup(
    plan: list[dict], kubectl_base: list[str], assume_yes: bool
) -> None:
    print("=== Phase 3: delete truly-orphaned leftover networks ===\n")
    if not plan:
        print("No orphaned leftover networks to delete.\n")
        return

    print(f"About to DELETE {len(plan)} orphaned network(s) — this is destructive:")
    for p in plan:
        print(
            f"  - network {p['network_id']} "
            f"(switch {p['switch_name']}, {p['port_count']} port(s)):"
        )
        for action in _orphan_actions(p):
            print(f"      {action}")
    if not _confirm("Apply these Phase 3 DELETIONS?", assume_yes):
        print("Skipped Phase 3 — no changes made.\n")
        return

    # One transaction per network so a failure on one (e.g. an unexpected
    # lingering reference) does not roll back the others.
    print(f"Deleting {len(plan)} orphaned network(s), one transaction each …")
    ok, failed = 0, 0
    for p in plan:
        result = _ovn_cmd(kubectl_base, NB_POD, "ovn-nbctl", *_orphan_txn_args(p))
        if result.returncode != 0:
            failed += 1
            log.error(
                "Failed deleting network %s (switch %s): %s",
                p["network_id"],
                p["switch_name"],
                result.stderr.strip(),
            )
            continue
        ok += 1
        print(f"  - {p['switch_name']} (network {p['network_id']}) removed")

    print(f"\nDone. {ok} removed, {failed} failed.")
    if failed:
        sys.exit(1)


def build_kubectl_base(kube_context: str | None) -> list[str]:
    cmd = ["kubectl"]
    if kube_context:
        cmd += ["--context", kube_context]
    return cmd


# --- Operator interaction: connection banner + explicit confirmation -------


def _confirm(prompt: str, assume_yes: bool) -> bool:
    """Pause for explicit operator confirmation before mutating anything."""
    if assume_yes:
        print(f"{prompt} [auto-confirmed via --yes]")
        return True
    try:
        answer = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        answer = ""
    return answer in ("y", "yes")


def _resolve_kube_context(kube_context: str | None) -> str:
    if kube_context:
        return kube_context
    result = subprocess.run(
        ["kubectl", "config", "current-context"], capture_output=True, text=True
    )
    return result.stdout.strip() or "(unknown)"


def _openstack_target(os_cloud: str | None) -> list[tuple[str, str]]:
    """(label, value) pairs describing the OpenStack target.

    Uses `openstack configuration show`, which masks secrets (e.g. password) by
    default, so no credentials are printed.
    """
    result = _openstack_cmd(os_cloud, "configuration", "show", "-f", "json")
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        return [("status", f"unavailable ({detail[-1] if detail else 'error'})")]
    try:
        cfg = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [("status", "unparsable configuration output")]
    pairs = [
        (label, cfg[key])
        for label, key in (
            ("auth URL", "auth.auth_url"),
            ("region", "region_name"),
            ("project", "auth.project_name"),
            ("username", "auth.username"),
        )
        if cfg.get(key)
    ]
    return pairs or [("status", "(no auth details in configuration)")]


def print_connection_banner(
    kube_context: str | None, os_cloud: str | None, phase3_enabled: bool, execute: bool
) -> None:
    mode = "EXECUTE (changes WILL be applied)" if execute else "DRY-RUN (no changes)"
    print("=" * 64)
    print("OVN HA_Chassis cleanup — target environment")
    print("=" * 64)
    print(f"  Mode               : {mode}")
    print(f"  Kubernetes context : {_resolve_kube_context(kube_context)}")
    print(f"  OVN namespace/pods : {OVN_NAMESPACE} (nb={NB_POD}, sb={SB_POD})")
    if phase3_enabled:
        if os_cloud:
            print(f"  OpenStack cloud    : {os_cloud}")
            for label, val in _openstack_target(os_cloud):
                print(f"    {label:<16} : {val}")
        else:
            print("  OpenStack cloud    : (not set — --os-cloud/OS_CLOUD required)")
    print("=" * 64)
    print(flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--context",
        metavar="KUBE_CONTEXT",
        dest="kube_context",
        default=None,
        help="Kubernetes context for kubectl (default: current context)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Apply changes. Without this flag only a dry-run report is printed.",
    )
    parser.add_argument(
        "--skip-repopulate",
        action="store_true",
        default=False,
        help="Only clean up stale HA_Chassis rows; don't repopulate empty "
        "per-network HCGs.",
    )
    parser.add_argument(
        "--delete-orphaned-networks",
        action="store_true",
        default=False,
        help="Phase 3 (DESTRUCTIVE, opt-in): tear down OVN Logical_Switches "
        "whose backing neutron network is gone (switch + ports + HCG). "
        "Requires admin OpenStack credentials (--os-cloud / OS_CLOUD).",
    )
    parser.add_argument(
        "--os-cloud",
        metavar="CLOUD",
        dest="os_cloud",
        default=os.environ.get("OS_CLOUD"),
        help="clouds.yaml entry used to query neutron for Phase 3 "
        "(default: $OS_CLOUD).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Override the Phase 3 safety tripwire that aborts when an "
        "implausibly large share of networks look orphaned.",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        dest="assume_yes",
        help="Skip the per-phase confirmation prompt (for non-interactive use). "
        "Only meaningful with --execute.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Enable debug logging.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    kubectl_base = build_kubectl_base(args.kube_context)

    print_connection_banner(
        args.kube_context,
        args.os_cloud,
        args.delete_orphaned_networks,
        args.execute,
    )

    log.info("Fetching live chassis from Southbound DB …")
    live_chassis = get_live_chassis_names(kubectl_base)
    log.info("Live chassis: %s", ", ".join(sorted(live_chassis)) or "(none)")

    log.info("Fetching HA_Chassis rows from Northbound DB …")
    all_ha_chassis = get_all_ha_chassis(kubectl_base)
    all_ha_chassis_by_uuid = {r["_uuid"]: r["chassis_name"] for r in all_ha_chassis}
    stale_rows = find_stale_ha_chassis(all_ha_chassis, live_chassis)
    stale_by_uuid = {r["_uuid"]: r for r in stale_rows}
    stale_uuids = set(stale_by_uuid)
    log.info("Found %d stale HA_Chassis row(s)", len(stale_rows))

    log.info("Fetching HA_Chassis_Group rows …")
    groups = get_all_ha_chassis_groups(kubectl_base)
    cleanup_records = map_groups_to_stale_members(groups, stale_uuids)

    if not args.execute:
        print_cleanup_report(cleanup_records, stale_by_uuid)
    else:
        execute_cleanup(cleanup_records, kubectl_base, args.assume_yes)

    if not args.skip_repopulate:
        log.info("Fetching Logical_Router_Port rows …")
        router_ports = get_all_router_ports(kubectl_base)
        plan, skipped = plan_repopulation(
            groups, all_ha_chassis_by_uuid, stale_uuids, router_ports
        )

        if not args.execute:
            print_repopulation_report(plan, skipped)
            if cleanup_records or plan:
                print("Run with --execute to apply the changes above.")
        else:
            execute_repopulation(plan, kubectl_base, args.assume_yes)

    if not args.delete_orphaned_networks:
        return

    if not args.os_cloud:
        print(
            "ERROR: --delete-orphaned-networks requires admin OpenStack "
            "credentials. Pass --os-cloud <clouds.yaml entry> or set OS_CLOUD.",
            file=sys.stderr,
        )
        sys.exit(1)

    log.info("Fetching Logical_Switch / port reference data for orphan check …")
    switches = get_all_logical_switches(kubectl_base)
    lsp_refs = build_hcg_ref_map(get_lsp_hcg_refs(kubectl_base))
    lrp_refs = build_hcg_ref_map(get_lrp_hcg_refs(kubectl_base))
    hcg_by_name = {g["name"]: g for g in groups}

    log.info("Querying neutron (%s) for live networks …", args.os_cloud)
    orphan_plan, orphan_skipped = plan_orphan_cleanup(
        switches, hcg_by_name, lsp_refs, lrp_refs, args.os_cloud, args.force
    )

    if not args.execute:
        print_orphan_report(orphan_plan, orphan_skipped)
        if orphan_plan:
            print("Run with --execute to apply the Phase 3 deletions above.")
    else:
        execute_orphan_cleanup(orphan_plan, kubectl_base, args.assume_yes)


if __name__ == "__main__":
    main()
