#!/usr/bin/env python3
"""Detect and clean up orphaned OVN uplink logical switch ports.

An uplink-* LSP that exists in the OVN Northbound DB but has no matching
Neutron port with the same name is orphaned — likely left over from testing
or an earlier bug.

Runs in dry-run mode by default. Pass --execute to delete the LSPs.
"""

import argparse
import json
import logging
import subprocess
import sys

import openstack
import openstack.exceptions

OVN_POD = "ovn-ovsdb-nb-0"
OVN_NAMESPACE = "openstack"

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


def _ovn_cmd(kubectl_base: list[str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        kubectl_base
        + ["exec", "-n", OVN_NAMESPACE, OVN_POD, "--", "ovn-nbctl"]
        + list(args),
        capture_output=True,
        text=True,
    )


def list_ovn_uplink_lsps(kubectl_base: list[str]) -> list[dict]:
    """Return [{lport_name, uuid, neutron_port_name}] for every uplink-* LSP.

    Two creation paths exist:
    - create_uplink_port() in routers.py: lport_name="uplink-{segment_id}",
      external_ids={}.  Matched by lport_name prefix.
    - Normal Neutron port sync: lport_name=<port-uuid>,
      external_ids["neutron:port_name"]="uplink-{segment_id}".  Matched by
      the external_ids field (shown as "aka" in ovn-nbctl show).
    """
    result = _ovn_cmd(
        kubectl_base,
        "--columns=name,_uuid,external_ids",
        "--format=json",
        "list",
        "logical_switch_port",
    )
    if result.returncode != 0:
        print(
            f"ERROR: ovn-nbctl list logical_switch_port failed:\n{result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    rows = parse_ovn_json(result.stdout)
    lsps = []
    for r in rows:
        lport_name = r.get("name", "")
        ext_ids = r.get("external_ids") or {}
        neutron_port_name = (
            ext_ids.get("neutron:port_name", "") if isinstance(ext_ids, dict) else ""
        )
        if lport_name.startswith("uplink-") or neutron_port_name.startswith("uplink-"):
            lsps.append(
                {
                    "lport_name": lport_name,
                    "uuid": r["_uuid"],
                    "neutron_port_name": neutron_port_name,
                }
            )
    return lsps


def build_lsp_network_map(kubectl_base: list[str]) -> dict[str, str]:
    """Return {port_uuid: network_id} for all ports on neutron-* switches."""
    result = _ovn_cmd(
        kubectl_base,
        "--columns=name,ports",
        "--format=json",
        "list",
        "logical_switch",
    )
    if result.returncode != 0:
        print(
            f"ERROR: ovn-nbctl list logical_switch failed:\n{result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    rows = parse_ovn_json(result.stdout)
    mapping: dict[str, str] = {}
    for row in rows:
        switch_name = row.get("name", "")
        if not isinstance(switch_name, str) or not switch_name.startswith("neutron-"):
            continue
        network_id = switch_name.removeprefix("neutron-")
        ports = row.get("ports", [])
        if isinstance(ports, str):
            # Single port unwrapped from ["uuid", "..."] to a bare string
            ports = [ports]
        for port_uuid in ports:
            if isinstance(port_uuid, str):
                mapping[port_uuid] = network_id
    return mapping


def verify_neutron_matches_ovn(conn, network_id: str, kubectl_base: list[str]) -> None:
    """Confirm Neutron knows about a network found in OVN; exit if not.

    A missing network most likely means --context and --os-cloud point at
    different clusters.
    """
    try:
        conn.network.find_network(network_id, ignore_missing=False)
    except openstack.exceptions.ResourceNotFound:
        context_hint = f" (context: {kubectl_base[2]})" if len(kubectl_base) > 1 else ""
        print(
            f"ERROR: Neutron does not know about network {network_id} that "
            f"OVN{context_hint} reports.\n"
            "This likely means --context and --os-cloud are pointing at different "
            "clusters.\nVerify that both flags target the same environment.",
            file=sys.stderr,
        )
        sys.exit(1)
    log.debug("Cluster sanity check passed: Neutron knows network %s", network_id)


def find_orphaned_lsps(conn, kubectl_base: list[str], verbose: bool) -> list[dict]:
    """Return one record per OVN uplink LSP that has no matching Neutron port."""
    log.info("Fetching OVN uplink LSPs …")
    lsps = list_ovn_uplink_lsps(kubectl_base)
    log.info("Found %d uplink LSP(s) in OVN", len(lsps))

    if not lsps:
        return []

    log.info("Building LSP → network map …")
    lsp_network = build_lsp_network_map(kubectl_base)

    # Sanity check: verify at least one OVN network is also visible in Neutron.
    sample_ids = [
        lsp_network[lsp["uuid"]] for lsp in lsps if lsp["uuid"] in lsp_network
    ]
    if sample_ids:
        verify_neutron_matches_ovn(conn, sample_ids[0], kubectl_base)

    log.info("Cross-checking %d LSP(s) against Neutron …", len(lsps))
    orphans: list[dict] = []
    for lsp in lsps:
        if lsp["neutron_port_name"]:
            # lport_name is the Neutron port UUID; look up directly by ID.
            port = conn.network.find_port(lsp["lport_name"], ignore_missing=True)
            exists = port is not None
            display_name = lsp["neutron_port_name"]
        else:
            # lport_name is "uplink-{segment_id}" (create_uplink_port path); look up by name.
            exists = bool(list(conn.network.ports(name=lsp["lport_name"])))
            display_name = lsp["lport_name"]

        if not exists:
            network_id = lsp_network.get(lsp["uuid"], "")
            log.debug(
                "Orphaned: %s (network %s)", display_name, network_id or "unknown"
            )
            orphans.append(
                {
                    "display_name": display_name,
                    "lport_name": lsp["lport_name"],
                    "uuid": lsp["uuid"],
                    "network_id": network_id,
                }
            )
        else:
            log.debug("OK: %s → Neutron port exists", display_name)

    return orphans


def print_dry_run_report(orphans: list[dict]) -> None:
    if not orphans:
        print("[DRY-RUN] No orphaned OVN uplink LSPs found.")
        return

    print(f"[DRY-RUN] Found {len(orphans)} orphaned OVN uplink LSP(s):\n")
    for o in orphans:
        print(f"[DRY-RUN]   Name   : {o['display_name']}")
        print(f"[DRY-RUN]   OVN ID : {o['lport_name']}")
        print(f"[DRY-RUN]   UUID   : {o['uuid']}")
        if o["network_id"]:
            print(f"[DRY-RUN]   Net    : {o['network_id']}")
        print(f"[DRY-RUN]   Action : ovn-nbctl lsp-del {o['lport_name']}")
        print()


def build_kubectl_base(kube_context: str | None) -> list[str]:
    cmd = ["kubectl"]
    if kube_context:
        cmd += ["--context", kube_context]
    return cmd


def execute_cleanup(orphans: list[dict], kubectl_base: list[str]) -> None:
    if not orphans:
        print("No orphaned OVN uplink LSPs found. Nothing to do.")
        return

    errors = 0
    for o in orphans:
        net_hint = f" (network {o['network_id']})" if o["network_id"] else ""
        print(f"Deleting OVN LSP {o['display_name']}{net_hint} …")
        result = _ovn_cmd(kubectl_base, "lsp-del", o["lport_name"])
        if result.returncode != 0:
            log.error(
                "  lsp-del %s failed (rc=%d): %s",
                o["lport_name"],
                result.returncode,
                result.stderr.strip(),
            )
            errors += 1
        else:
            print("  Deleted.")

    if errors:
        log.error("%d LSP(s) could not be deleted (see errors above).", errors)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--os-cloud",
        metavar="CLOUD",
        default=None,
        help="OpenStack cloud name from clouds.yaml (default: OS_CLOUD env var)",
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

    try:
        conn = openstack.connect(cloud=args.os_cloud)
    except Exception as exc:
        log.error("Failed to connect to OpenStack: %s", exc)
        sys.exit(1)

    kubectl_base = build_kubectl_base(args.kube_context)
    orphans = find_orphaned_lsps(conn, kubectl_base, verbose=args.verbose)

    if not args.execute:
        print_dry_run_report(orphans)
        if orphans:
            print("Run with --execute to apply the changes above.")
    else:
        execute_cleanup(orphans, kubectl_base)


if __name__ == "__main__":
    main()
