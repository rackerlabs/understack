#!/usr/bin/env python3
"""Detect and clean up orphaned uplink ports on flavored routers.

Before commit b54ef97e, a flavored router that was the first to connect to a
network would trigger creation of:
  - a shared Neutron port named uplink-{segment_id} (added as a trunk subport)
  - an OVN localnet LSP also named uplink-{segment_id}

These are now orphaned. This script finds and optionally removes them.

Runs in dry-run mode by default. Pass --execute to apply changes.
"""

import argparse
import logging
import subprocess
import sys

import openstack
import openstack.exceptions

DEVICE_OWNER_ROUTER_INTF = "network:router_interface"
OVN_POD = "ovn-ovsdb-nb-0"
OVN_NAMESPACE = "openstack"

log = logging.getLogger(__name__)


def build_subport_trunk_map(conn) -> dict[str, str]:
    """Return {subport_id: trunk_id} for every trunk in the cloud."""
    mapping: dict[str, str] = {}
    for trunk in conn.network.trunks():
        try:
            data = conn.network.get_trunk_subports(trunk.id)
            for sp in data.get("sub_ports", []):
                mapping[sp["port_id"]] = trunk.id
        except Exception as exc:
            log.warning("Could not fetch subports for trunk %s: %s", trunk.id, exc)
    return mapping


def find_orphaned_uplinks(conn, verbose: bool) -> list[dict]:
    """Return one record per orphaned uplink Neutron port."""
    log.info("Building subport → trunk reverse map …")
    subport_trunk = build_subport_trunk_map(conn)
    log.debug("Subport→trunk map: %d entries", len(subport_trunk))

    log.info("Listing routers …")
    flavored_routers = {r.id: r for r in conn.network.routers() if r.flavor_id}
    log.info("Found %d flavored router(s)", len(flavored_routers))

    if not flavored_routers:
        return []

    # network_id -> set of flavored router IDs that have an interface port there
    network_to_flavored: dict[str, set[str]] = {}
    for router_id in flavored_routers:
        for port in conn.network.ports(
            device_id=router_id,
            device_owner=DEVICE_OWNER_ROUTER_INTF,
        ):
            network_to_flavored.setdefault(port.network_id, set()).add(router_id)

    log.info("Flavored routers present on %d network(s)", len(network_to_flavored))

    orphans: list[dict] = []

    for network_id, flavored_ids_on_net in network_to_flavored.items():
        # All router-interface ports on this network
        all_intf_ports = list(
            conn.network.ports(
                network_id=network_id,
                device_owner=DEVICE_OWNER_ROUTER_INTF,
            )
        )
        all_router_ids = {p.device_id for p in all_intf_ports if p.device_id}

        # Routers on this network that are NOT in our flavored set are non-flavored
        unflavored_on_net = all_router_ids - flavored_ids_on_net
        if unflavored_on_net:
            log.debug(
                "Network %s: non-flavored router(s) %s present — uplink is "
                "legitimate, skipping",
                network_id,
                unflavored_on_net,
            )
            continue

        # Look for uplink ports on this network
        for port in conn.network.ports(network_id=network_id):
            if not (port.name and port.name.startswith("uplink-")):
                continue
            segment_id = port.name.removeprefix("uplink-")
            trunk_id = subport_trunk.get(port.id)
            orphans.append(
                {
                    "router_ids": sorted(flavored_ids_on_net),
                    "network_id": network_id,
                    "port_id": port.id,
                    "port_name": port.name,
                    "segment_id": segment_id,
                    "trunk_id": trunk_id,
                }
            )

    return orphans


def print_dry_run_report(orphans: list[dict]) -> None:
    if not orphans:
        print("[DRY-RUN] No orphaned uplink ports found.")
        return

    print(f"[DRY-RUN] Found {len(orphans)} orphaned uplink port(s):\n")
    for o in orphans:
        print(f"[DRY-RUN] Router(s) : {', '.join(o['router_ids'])}")
        print(f"[DRY-RUN]   Network : {o['network_id']}")
        print(f"[DRY-RUN]   Port    : {o['port_id']}  ({o['port_name']})")
        if o["trunk_id"]:
            print(
                f"[DRY-RUN]   1. Remove subport {o['port_id']} "
                f"from trunk {o['trunk_id']}"
            )
        else:
            print(
                f"[DRY-RUN]   1. WARN: port {o['port_id']} not found as a trunk "
                "subport — trunk removal step will be skipped"
            )
        print(f"[DRY-RUN]   2. Delete Neutron port {o['port_id']}")
        print(f"[DRY-RUN]   3. Delete OVN LSP uplink-{o['segment_id']}")
        print()


def build_kubectl_base(kube_context: str | None) -> list[str]:
    cmd = ["kubectl"]
    if kube_context:
        cmd += ["--context", kube_context]
    return cmd


def verify_ovn_matches_openstack(network_id: str, kubectl_base: list[str]) -> None:
    """Confirm OVN NB knows about network_id; exit if it does not.

    A missing switch most likely means --context and --os-cloud point at
    different clusters.
    """
    result = subprocess.run(
        kubectl_base
        + [
            "exec",
            "-n",
            OVN_NAMESPACE,
            OVN_POD,
            "--",
            "ovn-nbctl",
            "show",
            f"neutron-{network_id}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or network_id not in result.stdout:
        context_hint = f" (context: {kubectl_base[2]})" if len(kubectl_base) > 1 else ""
        print(
            f"ERROR: OVN NB{context_hint} has no switch for network {network_id}.\n"
            "This likely means --context and --os-cloud are pointing at different "
            "clusters.\nVerify that both flags target the same environment.",
            file=sys.stderr,
        )
        sys.exit(1)
    log.debug("OVN context verified: network %s is present in NB", network_id)


def execute_cleanup(conn, orphans: list[dict], kubectl_base: list[str]) -> None:
    if not orphans:
        print("No orphaned uplink ports found. Nothing to do.")
        return

    errors = 0
    for o in orphans:
        print(
            f"Cleaning up {o['port_name']} (port {o['port_id']}) "
            f"on network {o['network_id']} …"
        )

        # 1. Remove subport from trunk
        if o["trunk_id"]:
            print(f"  1. Removing subport from trunk {o['trunk_id']} …")
            try:
                conn.network.delete_trunk_subports(
                    o["trunk_id"], [{"port_id": o["port_id"]}]
                )
            except Exception as exc:
                log.error(
                    "  Failed to remove subport %s from trunk %s: %s",
                    o["port_id"],
                    o["trunk_id"],
                    exc,
                )
                errors += 1
                continue
        else:
            log.warning(
                "  Port %s is not a known trunk subport — skipping trunk removal",
                o["port_id"],
            )

        # 2. Delete Neutron port
        print(f"  2. Deleting Neutron port {o['port_id']} …")
        try:
            conn.network.delete_port(o["port_id"])
        except openstack.exceptions.ConflictException as exc:
            log.error("  Failed to delete Neutron port %s: %s", o["port_id"], exc)
            errors += 1
            continue
        except Exception as exc:
            log.error("  Unexpected error deleting port %s: %s", o["port_id"], exc)
            errors += 1
            continue

        # 3. Delete OVN localnet LSP  (non-fatal — Neutron port is already gone)
        lsp_name = f"uplink-{o['segment_id']}"
        print(f"  3. Deleting OVN LSP {lsp_name} …")
        result = subprocess.run(
            kubectl_base
            + [
                "exec",
                "-n",
                OVN_NAMESPACE,
                OVN_POD,
                "--",
                "ovn-nbctl",
                "lsp-del",
                lsp_name,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            log.warning(
                "  ovn-nbctl lsp-del %s failed (rc=%d): %s",
                lsp_name,
                result.returncode,
                result.stderr.strip(),
            )
        else:
            print(f"  OVN LSP {lsp_name} deleted.")

        print("  Done.\n")

    if errors:
        log.error("%d port(s) could not be cleaned up (see errors above).", errors)
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

    orphans = find_orphaned_uplinks(conn, verbose=args.verbose)

    kubectl_base = build_kubectl_base(args.kube_context)

    if orphans:
        verify_ovn_matches_openstack(orphans[0]["network_id"], kubectl_base)

    if not args.execute:
        print_dry_run_report(orphans)
        if orphans:
            print("Run with --execute to apply the changes above.")
    else:
        execute_cleanup(conn, orphans, kubectl_base)


if __name__ == "__main__":
    main()
