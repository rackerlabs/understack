from __future__ import annotations

import logging
from dataclasses import dataclass

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

logger = logging.getLogger(__name__)


@dataclass
class IronicPortgroupEvent:
    uuid: str
    name: str | None
    node_uuid: str
    address: str | None
    mode: str | None

    @classmethod
    def from_event_dict(cls, data: dict) -> IronicPortgroupEvent:
        payload = data.get("payload")
        if payload is None:
            raise Exception("Invalid event. No 'payload'")

        # Extract the actual data from the nested ironic object structure
        payload_data = payload.get("ironic_object.data")
        if payload_data is None:
            raise Exception("Invalid event. No 'ironic_object.data' in payload")

        return IronicPortgroupEvent(
            payload_data["uuid"],
            payload_data.get("name"),
            payload_data["node_uuid"],
            payload_data.get("address"),
            payload_data.get("mode"),
        )


def _get_node_name(conn: Connection, node_uuid: str) -> str | None:
    """Get the node name from Ironic by UUID."""
    try:
        node = conn.baremetal.get_node(node_uuid)  # pyright: ignore
        return node.name if node else None
    except Exception:
        logger.exception("Failed to get node %s from Ironic", node_uuid)
        return None


def _should_fix_portgroup_name(name: str | None, node_name: str) -> bool:
    """Check if portgroup name needs to be prefixed with node name."""
    if not name:
        return False
    return not name.startswith(f"{node_name}-")


def handle_portgroup_create(
    conn: Connection, _nautobot: Nautobot, event_data: dict
) -> int:
    """Handle Ironic Portgroup create event and fix name if needed."""
    event = IronicPortgroupEvent.from_event_dict(event_data)

    logger.info("Processing portgroup create event for %s", event.uuid)

    # Get the node name
    node_name = _get_node_name(conn, event.node_uuid)
    if not node_name:
        logger.error("Could not get node name for node %s", event.node_uuid)
        return 1

    # Check if name needs fixing
    if not _should_fix_portgroup_name(event.name, node_name):
        logger.info(
            "Portgroup %s name '%s' already has correct prefix", event.uuid, event.name
        )
        return 0

    # Fix the name by prefixing with node name
    new_name = f"{node_name}-{event.name}"
    logger.info(
        "Updating portgroup %s name from '%s' to '%s'",
        event.uuid,
        event.name,
        new_name,
    )

    try:
        conn.baremetal.update_port_group(event.uuid, name=new_name)  # pyright: ignore
        logger.info("Successfully updated portgroup %s name", event.uuid)
        return 0
    except Exception:
        logger.exception("Failed to update portgroup %s name", event.uuid)
        return 1
