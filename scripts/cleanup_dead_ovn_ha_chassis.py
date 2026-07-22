#!/usr/bin/env python3
"""Repair OVN HA_Chassis_Group state left behind by chassis decommissioning.

Two related problems, fixed in one pass:

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


def execute_cleanup(records: list[dict], kubectl_base: list[str]) -> None:
    print("=== Phase 1: stale HA_Chassis cleanup ===\n")
    if not records:
        print("No stale HA_Chassis rows found. Nothing to do.\n")
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
                "Multiple internal LRPs found for network %s on router %s; " "using %s",
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


def execute_repopulation(plan: list[dict], kubectl_base: list[str]) -> None:
    print("=== Phase 2: repopulate empty per-network HCGs ===\n")
    if not plan:
        print("No empty per-network HCGs to repopulate.\n")
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


def build_kubectl_base(kube_context: str | None) -> list[str]:
    cmd = ["kubectl"]
    if kube_context:
        cmd += ["--context", kube_context]
    return cmd


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
        execute_cleanup(cleanup_records, kubectl_base)

    if args.skip_repopulate:
        return

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
        execute_repopulation(plan, kubectl_base)


if __name__ == "__main__":
    main()
