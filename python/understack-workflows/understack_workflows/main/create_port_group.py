"""Create an Ironic port group for a baremetal node.

Accepts a node identifier (UUID or name) and creates a bonded port group
from the node's ports that have local_link_connection data, assigning
all eligible ports as members.
"""

import argparse
import logging
import os
import sys
import uuid as _uuid

from understack_workflows import helpers
from understack_workflows.openstack.client import get_openstack_client

logger = logging.getLogger(__name__)

ALLOWED_STATES = {"enroll", "inspecting", "inspect wait", "manageable"}


def parse_port_channel(port_id: str) -> str:
    """Derive a zero-padded port-channel suffix from a port_id string.

    Expects the numeric portion after the last '/' in the port_id.
    """
    tail = port_id.rsplit("/", 1)[-1]
    if not tail.isdigit():
        logger.error("Cannot derive numeric port-channel suffix from port_id='%s'", port_id)
        sys.exit(1)
    return f"{int(tail):02d}"


def create_port_group(node_id: str, dry_run: bool = False) -> None:
    """Create a port group for the given node (UUID or name).

    When dry_run is True, validates the node and reports what port group
    name would be created without making any changes.
    """
    os_cloud = os.getenv("OS_CLOUD", "understack")
    conn = get_openstack_client(cloud=os_cloud)

    try:
        _uuid.UUID(node_id)
    except ValueError:
        logger.warning(
            "Node identifier '%s' is not a UUID. Using a UUID is preferred "
            "as node names may be reassigned or changed.",
            node_id,
        )

    node = conn.baremetal.get_node(node_id)
    if node is None:
        logger.error("Node '%s' not found", node_id)
        sys.exit(1)

    state = (node.provision_state or "").lower()
    if state not in ALLOWED_STATES:
        logger.error(
            "Node %s is in state '%s', allowed: %s",
            node.id,
            node.provision_state,
            sorted(ALLOWED_STATES),
        )
        sys.exit(1)

    existing_pgs = list(conn.baremetal.port_groups(node=node.id))
    if existing_pgs:
        logger.error("Port group already exists for node %s", node.id)
        sys.exit(1)

    ports = list(conn.baremetal.ports(node=node.id, details=True))
    eligible = []
    for port in ports:
        llc = getattr(port, "local_link_connection", None) or {}
        if llc and llc.get("port_id"):
            eligible.append(port)

    if not eligible:
        logger.error("No ports with local_link_connection.port_id found for node %s", node.id)
        sys.exit(1)

    def sort_key(port):
        llc = port.local_link_connection or {}
        return (
            llc.get("switch_info") or "",
            llc.get("port_id") or "",
            port.address or "",
        )

    primary = sorted(eligible, key=sort_key)[0]
    llc = primary.local_link_connection or {}
    port_channel = parse_port_channel(llc["port_id"])

    mac = (primary.address or "").strip()
    if not mac:
        logger.error("Primary port %s is missing MAC address", primary.id)
        sys.exit(1)

    node_name = node.name or node.id
    pg_name = f"{node_name}-port-channel1{port_channel}"

    if dry_run:
        logger.info("[dry-run] Would create port group '%s' for node %s", pg_name, node.id)
        logger.info("[dry-run] MAC: %s | Eligible ports: %d", mac, len(eligible))
        for port in eligible:
            port_llc = port.local_link_connection or {}
            logger.info(
                "[dry-run]   port %s switch=%s port_id=%s",
                port.id,
                port_llc.get("switch_info", ""),
                port_llc.get("port_id", ""),
            )
        return

    logger.info("Creating port group '%s' for node %s with MAC %s", pg_name, node.id, mac)

    pg = conn.baremetal.create_port_group(
        node_id=node.id,
        name=pg_name,
        address=mac,
        mode="802.3ad",
        properties={
            "miimon": "100",
            "xmit_hash_policy": "layer2+3",
            "lacp_rate": "normal",
        },
        is_standalone_ports_supported=True,
    )

    for port in eligible:
        logger.info("Assigning port %s -> port group %s", port.id, pg.id)
        conn.baremetal.update_port(port.id, port_group_id=pg.id)

    logger.info("Created port group %s with %d member port(s)", pg.id, len(eligible))


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Create an Ironic port group for a baremetal node",
    )
    parser.add_argument(
        "node",
        help="Node UUID or name",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report the port group name that would be created without making changes",
    )
    return parser


def main() -> None:
    helpers.setup_logger()
    args = argument_parser().parse_args()
    create_port_group(node_id=args.node, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
