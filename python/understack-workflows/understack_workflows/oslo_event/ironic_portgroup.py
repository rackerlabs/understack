from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

import pynautobot.core.query
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
        """Extract LAG interface name by stripping node name prefix.

        Expected format: $NODENAME_$INTERFACE (using underscore separator)
        Example: "server-123_bond0" -> "bond0"
        """
        if not self.name:
            return self.uuid

        # Strip the node name prefix: "nodename_interface" -> "interface"
        try:
            if "_" in self.name:
                parts = self.name.split("_", 1)
                if len(parts) == 2:
                    return parts[1]
                # If split didn't produce 2 parts, return as-is
                logger.warning(
                    "Portgroup name '%s' has underscore but unexpected format",
                    self.name,
                )
                return self.name
            else:
                # If no underscore, return as-is (shouldn't happen after validation)
                logger.warning(
                    "Portgroup name '%s' does not contain underscore separator",
                    self.name,
                )
                return self.name
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


def handle_portgroup_create_update(
    _conn: Connection, nautobot: Nautobot, event_data: dict
) -> int:
    """Sync Ironic Portgroup to Nautobot LAG interface."""
    event = IronicPortgroupEvent.from_event_dict(event_data)

    logger.debug("Looking up LAG interface %s in Nautobot", event.uuid)
    lag_intf = nautobot.dcim.interfaces.get(id=event.uuid)

    # Prepare LAG interface attributes
    attrs = {
        "name": event.lag_name,
        "device": event.node_uuid,
        "type": "lag",
        "status": "Active",
    }

    if event.address:
        attrs["mac_address"] = event.address

    if event.mode:
        attrs["description"] = f"Bond mode: {event.mode}"

    if not lag_intf:
        # Create new LAG interface
        logger.info("Creating LAG interface %s in Nautobot", event.uuid)
        attrs["id"] = event.uuid

        try:
            lag_intf = nautobot.dcim.interfaces.create(**attrs)
            logger.info("Created LAG interface %s", event.uuid)
        except pynautobot.core.query.RequestError as e:
            # Handle race condition - another workflow created the interface
            if e.req.status_code == 400 and "unique set" in str(e).lower():
                logger.info("LAG interface %s already exists, fetching", event.uuid)
                lag_intf = nautobot.dcim.interfaces.get(id=event.uuid)
                if not lag_intf:
                    logger.error("LAG interface %s not found", event.uuid)
                    return 1
            else:
                logger.exception("Failed to create LAG interface %s", event.uuid)
                return 1
        except Exception:
            logger.exception("Failed to create LAG interface %s", event.uuid)
            return 1

    # Update LAG interface attributes
    logger.debug("Updating LAG interface %s", event.uuid)
    for key, value in attrs.items():
        if key != "id":  # Don't update ID
            setattr(lag_intf, key, value)

    try:
        cast(Record, lag_intf).save()
        logger.info("LAG interface %s synced to Nautobot", event.uuid)
    except Exception:
        logger.exception("Failed to update LAG interface %s", event.uuid)
        return 1

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
