from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot
from pynautobot.core.response import Record

logger = logging.getLogger(__name__)

# TODO: we should not hardcode this
INTERFACE_TYPE = "25gbase-x-sfp28"


@dataclass
class IronicPortEvent:
    uuid: str
    name: str
    address: str
    node_uuid: str
    physical_network: str
    pxe_enabled: bool
    remote_port_id: str | None
    remote_switch_info: str | None
    remote_switch_id: str | None

    @property
    def interface_name(self) -> str:
        try:
            if self.name:
                return self.name
            return self.uuid
        except Exception:
            return self.uuid

    @classmethod
    def from_event_dict(cls, data: dict) -> IronicPortEvent:
        payload = data.get("payload")
        if payload is None:
            raise Exception("Invalid event. No 'payload'")

        # Extract the actual data from the nested ironic object structure
        payload_data = payload.get("ironic_object.data")
        if payload_data is None:
            raise Exception("Invalid event. No 'ironic_object.data' in payload")

        llc = payload_data.get("local_link_connection") or {}

        return IronicPortEvent(
            payload_data["uuid"],
            payload_data.get("name") or "",  # ensures we always have a string
            payload_data["address"],
            payload_data["node_uuid"],
            payload_data.get("physical_network") or "",
            payload_data.get("pxe_enabled") or False,
            llc.get("port_id"),
            llc.get("switch_info"),
            llc.get("switch_id"),
        )


def handle_port_create_update(
    _conn: Connection, nautobot: Nautobot, event_data: dict
) -> int:
    """Sync Ironic Port to Nautobot interface."""
    event = IronicPortEvent.from_event_dict(event_data)

    logger.debug("Looking up interface %s in Nautobot", event.uuid)
    intf = nautobot.dcim.interfaces.get(id=event.uuid)

    # Prepare interface attributes
    attrs = {
        "name": event.interface_name,
        "type": INTERFACE_TYPE,
        "status": "Active",
        "mac_address": event.address,
        "device": event.node_uuid,
    }

    if not intf:
        # Create new interface
        logger.info("Creating interface %s in Nautobot", event.uuid)
        attrs["id"] = event.uuid

        try:
            intf = nautobot.dcim.interfaces.create(**attrs)
            logger.info("Created interface %s", event.uuid)
        except Exception as e:
            # Handle race condition - another workflow created the interface
            if "unique set" in str(e).lower():
                logger.info("Interface %s already exists, fetching", event.uuid)
                intf = nautobot.dcim.interfaces.get(id=event.uuid)
                if not intf:
                    logger.error("Interface %s not found", event.uuid)
                    return 1
            else:
                logger.exception("Failed to create interface %s", event.uuid)
                return 1

    # Update interface attributes
    logger.debug("Updating interface %s", event.uuid)
    for key, value in attrs.items():
        if key != "id":  # Don't update ID
            setattr(intf, key, value)

    try:
        cast(Record, intf).save()
        logger.info("Interface %s synced to Nautobot", event.uuid)
    except Exception:
        logger.exception("Failed to update interface %s", event.uuid)
        return 1

    # Handle cable management if we have remote switch connection information
    if event.remote_port_id and event.remote_switch_info:
        return _handle_cable_management(nautobot, intf, event)

    logger.debug("No remote connection info available for interface %s", event.uuid)
    return 0


def _create_cable(nautobot: Nautobot, switch_intf, event: IronicPortEvent) -> int:
    """Create a new cable between the machine and switch."""
    try:
        cable = nautobot.dcim.cables.create(
            termination_a_type="dcim.interface",
            termination_a_id=event.uuid,
            termination_b_type="dcim.interface",
            termination_b_id=switch_intf.id,
            status="Connected",
        )
        logger.info(
            "Created cable %s connecting interface %s to %s:%s",
            cable.id,  # type: ignore
            event.uuid,
            event.remote_switch_info,
            event.remote_port_id,
        )
        return 0
    except Exception:
        logger.exception(
            "Failed to create cable connecting interface %s to %s:%s",
            event.uuid,
            event.remote_switch_info,
            event.remote_port_id,
        )
        return 1


def _update_existing_cable(cable, switch_intf, event: IronicPortEvent) -> int:
    """Handle updating an existing cable."""
    logger.debug("Interface %s has existing cable %s ", event.uuid, cable.id)
    # check both sides
    if (
        cable.termination_a_id == event.uuid
        and cable.termination_b_id == switch_intf.id
    ) or (
        cable.termination_b_id == event.uuid
        and cable.termination_a_id == switch_intf.id
    ):
        logger.info(
            "Cable already exists correctly connecting interface %s to %s:%s",
            event.uuid,
            event.remote_switch_info,
            event.remote_port_id,
        )
        return 0
    # cable connected to something else so update it
    cable.termination_a_id = event.uuid
    cable.termination_a_type = "dcim.interface"
    cable.termination_b_id = switch_intf.id
    cable.termination_b_type = "dcim.interface"
    cable.status = "Connected"
    cable.save()
    logger.info("Cable %s updated successfully", cable.id)
    return 0


def _handle_cable_management(
    nautobot: Nautobot, server_intf, event: IronicPortEvent
) -> int:
    """Handle cable creation/update for port events with remote connection info."""
    logger.debug(
        "Handling cable management for interface %s -> %s:%s",
        event.uuid,
        event.remote_switch_info,
        event.remote_port_id,
    )

    # Find the switch interface by name
    switch_intf = nautobot.dcim.interfaces.get(
        device=event.remote_switch_info,
        name=event.remote_port_id,
    )
    if not switch_intf:
        logger.error(
            "Switch interface %s not found on device %s, cannot create cable",
            event.remote_port_id,
            event.remote_switch_info,
        )
        return 1

    switch_intf = cast(Record, switch_intf)

    if cable := server_intf.cable:
        return _update_existing_cable(cable, switch_intf, event)
    else:
        return _create_cable(nautobot, switch_intf, event)


def handle_port_delete(_conn: Connection, nautobot: Nautobot, event_data: dict) -> int:
    """Operates on an Ironic Port delete event."""
    event = IronicPortEvent.from_event_dict(event_data)

    logger.debug("Handling port delete for interface %s", event.uuid)

    # Find the interface in Nautobot
    intf = nautobot.dcim.interfaces.get(id=event.uuid)
    if not intf:
        logger.debug(
            "Interface %s not found in Nautobot, nothing to delete", event.uuid
        )
        return 0

    # Find and delete any existing cable connected to this interface
    existing_cable = nautobot.dcim.cables.get(
        termination_a_type="dcim.interface",
        termination_a_id=intf.id,  # type: ignore
    )

    if existing_cable:
        logger.info("Deleting cable %s for interface %s", existing_cable.id, event.uuid)  # type: ignore
        cast(Record, existing_cable).delete()

    # Delete the interface
    logger.info("Deleting interface %s from Nautobot", event.uuid)
    cast(Record, intf).delete()

    return 0
