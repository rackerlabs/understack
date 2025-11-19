from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot
from pynautobot.core.response import Record

logger = logging.getLogger(__name__)


@dataclass
class IronicPortgroupEvent:
    uuid: str
    name: str | None
    node_uuid: str
    address: str | None
    mode: str | None
    properties: dict
    standalone_ports_supported: bool

    @property
    def lag_name(self) -> str:
        """Extract LAG interface name by stripping node name prefix."""
        if not self.name:
            return self.uuid

        # Strip the node name prefix: "nodename-interface" -> "interface"
        # Handle both formats: "node-name-interface" and "nodename:interface"
        try:
            # Try colon separator first (legacy format)
            if ":" in self.name:
                return self.name.split(":", 1)[1]

            # Try dash separator - need to find where node name ends
            # We'll look for common interface patterns after the node name
            parts = self.name.split("-")

            # Common interface prefixes that indicate start of interface name
            interface_prefixes = ["bond", "port", "lag", "ae", "po", "team", "br"]

            for i, part in enumerate(parts):
                if part.lower() in interface_prefixes or part.lower().startswith(
                    tuple(interface_prefixes)
                ):
                    return "-".join(parts[i:])

            # If no common prefix found, assume last part is the interface
            # or return the whole name if it's just one part
            return parts[-1] if len(parts) > 1 else self.name
        except Exception:
            logger.warning(
                "Could not parse LAG interface name from '%s', using as-is", self.name
            )
            return self.name

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
            payload_data.get("properties") or {},
            payload_data.get("standalone_ports_supported", True),
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


def handle_portgroup_create_update(
    conn: Connection, nautobot: Nautobot, event_data: dict
) -> int:
    """Handle Ironic Portgroup create and update events."""
    event = IronicPortgroupEvent.from_event_dict(event_data)

    logger.info("Processing portgroup create/update event for %s", event.uuid)

    # Get the node name
    node_name = _get_node_name(conn, event.node_uuid)
    if not node_name:
        logger.error("Could not get node name for node %s", event.node_uuid)
        return 1

    # Check if name needs fixing in Ironic
    if event.name and _should_fix_portgroup_name(event.name, node_name):
        new_name = f"{node_name}-{event.name}"
        logger.info(
            "Updating portgroup %s name from '%s' to '%s'",
            event.uuid,
            event.name,
            new_name,
        )
        try:
            conn.baremetal.update_port_group(event.uuid, name=new_name)  # pyright: ignore
            logger.info("Successfully updated portgroup %s name in Ironic", event.uuid)
            # Update the event object with the new name
            event.name = new_name
        except Exception:
            logger.exception("Failed to update portgroup %s name in Ironic", event.uuid)
            # Continue to create/update in Nautobot anyway

    # Create or update LAG interface in Nautobot
    logger.debug("Looking up LAG interface in Nautobot by UUID: %s", event.uuid)
    lag_intf = nautobot.dcim.interfaces.get(id=event.uuid)

    if not lag_intf:
        logger.debug(
            "Looking up LAG interface in Nautobot by device %s and name %s",
            event.node_uuid,
            event.lag_name,
        )
        lag_intf = nautobot.dcim.interfaces.get(
            device=event.node_uuid, name=event.lag_name
        )

    if not lag_intf:
        logger.info("No LAG interface found in Nautobot, creating")
        attrs = {
            "id": event.uuid,
            "name": event.lag_name,
            "device": event.node_uuid,
            "type": "lag",  # This is the key - LAGs are interfaces with type="lag"
            "status": "Active",
            "mode": event.mode or "access",  # Interface mode (access, tagged, etc.)
        }

        # Add MAC address if available
        if event.address:
            attrs["mac_address"] = event.address

        # Add description with bonding mode info
        if event.mode:
            attrs["description"] = f"Portgroup with mode: {event.mode}"

        try:
            lag_intf = nautobot.dcim.interfaces.create(**attrs)
            logger.info("Created LAG interface %s in Nautobot", event.uuid)
        except Exception:
            logger.exception(
                "Failed to create LAG interface %s in Nautobot", event.uuid
            )
            return 1
    else:
        logger.info("Existing LAG interface found in Nautobot, updating")
        lag_intf.name = event.lag_name  # type: ignore
        lag_intf.status = "Active"  # type: ignore
        lag_intf.type = "lag"  # type: ignore

        if event.address:
            lag_intf.mac_address = event.address  # type: ignore

        if event.mode:
            lag_intf.description = f"Portgroup with mode: {event.mode}"  # type: ignore

        try:
            cast(Record, lag_intf).save()
            logger.info("Updated LAG interface %s in Nautobot", event.uuid)
        except Exception:
            logger.exception(
                "Failed to update LAG interface %s in Nautobot", event.uuid
            )
            return 1

    logger.info("LAG interface %s in sync with Nautobot", event.uuid)
    return 0


def handle_portgroup_delete(
    _conn: Connection, nautobot: Nautobot, event_data: dict
) -> int:
    """Handle Ironic Portgroup delete event."""
    event = IronicPortgroupEvent.from_event_dict(event_data)

    logger.debug("Handling portgroup delete for LAG interface %s", event.uuid)

    # Find the LAG interface in Nautobot
    lag_intf = nautobot.dcim.interfaces.get(id=event.uuid)
    if not lag_intf:
        logger.debug(
            "LAG interface %s not found in Nautobot, nothing to delete", event.uuid
        )
        return 0

    # Delete the LAG interface
    logger.info("Deleting LAG interface %s from Nautobot", event.uuid)
    try:
        cast(Record, lag_intf).delete()
        logger.info("Successfully deleted LAG interface %s from Nautobot", event.uuid)
        return 0
    except Exception:
        logger.exception("Failed to delete LAG interface %s from Nautobot", event.uuid)
        return 1
