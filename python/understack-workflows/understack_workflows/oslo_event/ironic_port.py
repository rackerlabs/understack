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
            return self.name.split(":")[1]
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
    """Operates on an Ironic Port create and update event."""
    event = IronicPortEvent.from_event_dict(event_data)

    logger.debug("looking up interface in nautobot by UUID: %s", event.uuid)
    intf = nautobot.dcim.interfaces.get(id=event.uuid)
    if not intf:
        logger.debug(
            "looking up interface in nautobot by device %s and name %s",
            event.node_uuid,
            event.interface_name,
        )
        intf = nautobot.dcim.interfaces.get(
            device=event.node_uuid, name=event.interface_name
        )

    if not intf:
        logger.info("No interface found in nautobot, creating")
        attrs = {
            "id": event.uuid,
            "name": event.interface_name,
            "type": INTERFACE_TYPE,
            "status": "Active",
            "mac_address": event.address,
            "device": event.node_uuid,
        }
        intf = nautobot.dcim.interfaces.create(**attrs)
    else:
        logger.info("Existing interface found in nautobot, updating")
        intf.name = event.interface_name  # type: ignore
        intf.type = INTERFACE_TYPE  # type: ignore
        intf.status = "Active"  # type: ignore
        intf.mac_address = event.address  # type: ignore
        cast(Record, intf).save()

    logger.info("Interface %s in sync with nautobot", event.uuid)

    # Handle cable management if we have remote switch connection information
    if event.remote_port_id and event.remote_switch_info:
        _handle_cable_management(nautobot, intf, event)
    else:
        logger.debug("No remote connection info available for interface %s", event.uuid)

    return 0


def _handle_cable_management(
    nautobot: Nautobot, server_interface, event: IronicPortEvent
):
    """Handle cable creation/update for port events with remote connection info."""
    logger.debug(
        "Handling cable management for interface %s -> %s:%s",
        event.uuid,
        event.remote_switch_info,
        event.remote_port_id,
    )

    # Find the switch device by name
    switch_device = nautobot.dcim.devices.get(name=event.remote_switch_info)
    if not switch_device:
        logger.warning(
            "Switch device %s not found in Nautobot, cannot create cable",
            event.remote_switch_info,
        )
        return

    # Find the switch interface by name
    switch_interface = nautobot.dcim.interfaces.get(
        device=switch_device.id,  # type: ignore
        name=event.remote_port_id,  # type: ignore
    )
    if not switch_interface:
        logger.warning(
            "Switch interface %s not found on device %s, cannot create cable",
            event.remote_port_id,
            event.remote_switch_info,
        )
        return

    # Check if there's an existing cable connected to the server interface
    existing_cable = cast(
        Record,
        nautobot.dcim.cables.get(
            termination_a_type="dcim.interface",
            termination_a_id=server_interface.id,
        ),
    )

    if existing_cable:
        # Check if the existing cable connects to the correct switch interface
        if (
            existing_cable.termination_b_type == "dcim.interface"  # type: ignore
            and existing_cable.termination_b_id == switch_interface.id  # type: ignore
        ):
            logger.info(
                "Cable already exists correctly connecting interface %s to %s:%s",
                event.uuid,
                event.remote_switch_info,
                event.remote_port_id,
            )
            return
        else:
            # Cable exists but connects to wrong interface, update it
            logger.info(
                "Updating existing cable %s to connect to switch interface %s:%s",
                existing_cable.id,  # type: ignore
                event.remote_switch_info,
                event.remote_port_id,
            )
            existing_cable.termination_b_type = "dcim.interface"  # type: ignore
            existing_cable.termination_b_id = switch_interface.id  # type: ignore
            existing_cable.save()
            logger.info("Cable %s updated successfully", existing_cable.id)
            return

    # No existing cable, create a new one
    cable_attrs = {
        "termination_a_type": "dcim.interface",
        "termination_a_id": server_interface.id,
        "termination_b_type": "dcim.interface",
        "termination_b_id": switch_interface.id,  # type: ignore
        "status": "Connected",
    }

    try:
        cable = nautobot.dcim.cables.create(**cable_attrs)
        logger.info(
            "Created cable %s connecting interface %s to %s:%s",
            cable.id,  # type: ignore
            event.uuid,
            event.remote_switch_info,
            event.remote_port_id,
        )
    except Exception as e:
        logger.error(
            "Failed to create cable connecting interface %s to %s:%s: %s",
            event.uuid,
            event.remote_switch_info,
            event.remote_port_id,
            e,
        )


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
