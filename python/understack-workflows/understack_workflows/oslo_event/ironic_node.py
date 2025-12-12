from __future__ import annotations

from typing import Self
from typing import cast
from uuid import UUID

from ironicclient.common.apiclient import exceptions as ironic_exceptions
from ironicclient.v1.node import Node
from openstack.connection import Connection
from openstack.exceptions import ConflictException
from pydantic import BaseModel
from pydantic import computed_field
from pynautobot.core.api import Api as Nautobot
from pynautobot.core.response import Record

from understack_workflows.helpers import save_output
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.ironic.provision_state_mapper import ProvisionStateMapper
from understack_workflows.oslo_event.keystone_project import is_project_svm_enabled

logger = setup_logger(__name__)


class IronicNodeEvent(BaseModel):
    """Represents an Ironic node create/update/delete event - minimal event data."""

    uuid: str

    @classmethod
    def from_event_dict(cls, data: dict) -> Self:
        """Parse Ironic node event from Oslo notification payload to extract UUID."""
        payload = data.get("payload")
        if payload is None:
            raise ValueError("Invalid event. No 'payload'")

        # Extract the actual data from the nested ironic object structure
        payload_data = payload.get("ironic_object.data")
        if payload_data is None:
            raise ValueError("Invalid event. No 'ironic_object.data' in payload")

        return cls(uuid=payload_data["uuid"])


class IronicProvisionSetEvent(BaseModel):
    owner: UUID
    lessee: UUID
    instance_uuid: UUID
    node_uuid: UUID
    event: str

    @classmethod
    def from_event_dict(cls, data: dict) -> Self:
        payload = data.get("payload")
        if payload is None:
            raise ValueError("invalid event")

        payload_data = payload.get("ironic_object.data")
        if payload_data is None:
            raise ValueError("Invalid event. No 'ironic_object.data' in payload")

        return cls(
            owner=payload_data["owner"],
            lessee=payload_data["lessee"],
            instance_uuid=payload_data["instance_uuid"],
            event=payload_data["event"],
            node_uuid=payload_data["uuid"],
        )

    @computed_field
    @property
    def lessee_undashed(self) -> str:
        """Returns lessee without dashes."""
        return self.lessee.hex


def extract_serial_from_node(node: Node, inventory: dict | None = None) -> str | None:
    """Extract serial number from node data.

    Args:
        node: Ironic Node object
        inventory: Optional inventory data from Ironic

    Returns:
        Serial number if found, None otherwise
    """
    # Try multiple sources for serial number
    # 1. Check properties.serial_number
    if hasattr(node, "properties") and node.properties:
        if serial := node.properties.get("serial_number"):
            return serial

    # 2. Check extra.system.serial_number (from hardware inspection)
    if hasattr(node, "extra") and node.extra:
        if system := node.extra.get("system"):
            if serial := system.get("serial_number"):
                return serial

    # 3. Check inventory data if provided
    if inventory:
        if (
            serial := inventory.get("inventory", {})
            .get("system_vendor", {})
            .get("serial_number")
        ):
            return serial

    # 4. No serial found
    return None


def map_provision_state_to_status(provision_state: str | None) -> str:
    """Map Ironic provision state to Nautobot device status."""
    if not provision_state:
        return "Planned"

    # Use the existing ProvisionStateMapper
    status = ProvisionStateMapper.translate_to_nautobot(provision_state)
    # If the mapper returns None (intermediate state), default to Planned
    return status if status is not None else "Planned"


def handle_node_create_update(
    conn: Connection, nautobot: Nautobot, event_data: dict
) -> int:
    """Sync Ironic Node to Nautobot device.

    Handles both node.create.end and node.update.end events.
    Fetches full node data from Ironic API instead of relying on event payload.
    """
    try:
        event = IronicNodeEvent.from_event_dict(event_data)
    except (ValueError, KeyError) as e:
        logger.error("Failed to parse node event: %s", e)
        return 1

    # Initialize Ironic client and fetch full node data
    try:
        ironic = IronicClient()
        node = ironic.get_node(event.uuid)
        logger.debug("Fetched node %s from Ironic API", event.uuid)
    except ironic_exceptions.NotFound:
        logger.error("Node %s not found in Ironic", event.uuid)
        return 1
    except Exception:
        logger.exception("Failed to fetch node %s from Ironic", event.uuid)
        return 1

    # Check if node has required fields
    if not node.uuid or not node.name:
        logger.warning(
            "Node %s lacks required fields (uuid, name) for Nautobot sync, skipping",
            event.uuid,
        )
        return 0

    # Try to fetch inventory for serial number
    inventory = None
    try:
        inventory = ironic.get_node_inventory(event.uuid)
        logger.debug("Fetched inventory for node %s", event.uuid)
    except ironic_exceptions.NotFound:
        logger.debug("No inventory data available for node %s", event.uuid)
    except Exception:
        logger.warning("Failed to fetch inventory for node %s, continuing", event.uuid)

    logger.debug("Looking up device %s in Nautobot", event.uuid)
    device = nautobot.dcim.devices.get(id=event.uuid)

    # Prepare device attributes
    attrs = {
        "name": node.name,
        "status": map_provision_state_to_status(node.provision_state),
    }

    # Add optional fields if available
    if serial := extract_serial_from_node(node, inventory):
        attrs["serial"] = serial

    # Add tenant (lessee) if available
    if hasattr(node, "lessee") and node.lessee:
        try:
            # Convert lessee UUID to tenant in Nautobot
            tenant_uuid = (
                UUID(node.lessee) if isinstance(node.lessee, str) else node.lessee
            )
            # Note: This assumes tenant exists in Nautobot with matching UUID
            attrs["tenant"] = str(tenant_uuid)
            logger.debug("Setting tenant to %s", tenant_uuid)
        except (ValueError, AttributeError) as e:
            logger.warning("Invalid lessee UUID %s: %s", node.lessee, e)

    # Add custom fields for Ironic-specific data
    custom_fields = {}
    if node.provision_state:
        custom_fields["ironic_provision_state"] = node.provision_state
    if node.resource_class:
        custom_fields["resource_class"] = node.resource_class

    # Add hardware specs to custom fields from node properties
    if hasattr(node, "properties") and node.properties:
        if memory_mb := node.properties.get("memory_mb"):
            custom_fields["memory_mb"] = memory_mb
        if cpus := node.properties.get("cpus"):
            custom_fields["cpus"] = cpus
        if cpu_arch := node.properties.get("cpu_arch"):
            custom_fields["cpu_arch"] = cpu_arch
        if local_gb := node.properties.get("local_gb"):
            custom_fields["local_gb"] = local_gb

    if custom_fields:
        attrs["custom_fields"] = custom_fields

    if not device:
        # Create new device
        logger.info("Creating device %s in Nautobot", event.uuid)
        attrs["id"] = event.uuid

        # Note: Device creation in Nautobot requires device_type and location
        # These should be configured via environment variables or cluster metadata
        # For now, we log a warning and skip creation if device doesn't exist
        # The device should be pre-created in Nautobot or this handler should be
        # enhanced to map resource_class to device_type and get location from config
        logger.warning(
            "Device %s not found in Nautobot. Device creation requires "
            "device_type and location configuration. Skipping creation.",
            event.uuid,
        )
        return 0

    # Update existing device
    logger.debug("Updating device %s", event.uuid)
    for key, value in attrs.items():
        if key != "id":  # Don't update ID
            setattr(device, key, value)

    try:
        cast(Record, device).save()
        logger.info("Device %s synced to Nautobot", event.uuid)
        return 0
    except Exception:
        logger.exception("Failed to update device %s", event.uuid)
        return 1


def handle_node_delete(conn: Connection, nautobot: Nautobot, event_data: dict) -> int:
    """Remove Ironic Node from Nautobot.

    Handles node.delete.end events.
    """
    try:
        event = IronicNodeEvent.from_event_dict(event_data)
    except (ValueError, KeyError) as e:
        logger.error("Failed to parse node delete event: %s", e)
        return 1

    logger.debug("Handling node delete for device %s", event.uuid)

    # Find the device in Nautobot
    device = nautobot.dcim.devices.get(id=event.uuid)
    if not device:
        logger.debug("Device %s not found in Nautobot, nothing to delete", event.uuid)
        return 0

    # Delete the device (this will cascade to interfaces and cables)
    logger.info("Deleting device %s from Nautobot", event.uuid)
    try:
        cast(Record, device).delete()
        logger.info("Successfully deleted device %s from Nautobot", event.uuid)
        return 0
    except Exception:
        logger.exception("Failed to delete device %s from Nautobot", event.uuid)
        return 1


def handle_provision_end(conn: Connection, _: Nautobot, event_data: dict) -> int:
    """Operates on an Ironic Node provisioning END event."""
    payload = event_data.get("payload", {})
    payload_data = payload.get("ironic_object.data")

    if payload_data:
        previous_provision_state = payload_data.get("previous_provision_state")
        if previous_provision_state != "deploying":
            logger.info(
                "Skipping storage setup for previous_provision_state: %s",
                previous_provision_state,
            )
            return 0
    # Check if the project is configured with tags.
    event = IronicProvisionSetEvent.from_event_dict(event_data)
    logger.info("Checking if project %s is tagged with UNDERSTACK_SVM", event.lessee)
    if not is_project_svm_enabled(conn, event.lessee_undashed):
        return 0

    # Check if the server instance has an appropriate property.
    logger.info("Looking up Nova instance %s", event.instance_uuid)
    server = conn.get_server_by_id(event.instance_uuid)

    if not server:
        logger.error("Server %s not found", event.instance_uuid)
        save_output("storage", "not-found")
        return 1

    if server.metadata.get("storage") == "wanted":
        save_output("storage", "wanted")
    else:
        logger.info("Server %s did not want storage enabled.", server.id)
        save_output("storage", "not-set")

    save_output("node_uuid", str(event.node_uuid))
    save_output("instance_uuid", str(event.instance_uuid))

    create_volume_connector(conn, event)
    return 0


def create_volume_connector(conn: Connection, event: IronicProvisionSetEvent):
    logger.info("Creating baremetal volume connector.")
    try:
        connector = conn.baremetal.create_volume_connector(  # pyright: ignore
            node_uuid=event.node_uuid,
            type="iqn",
            connector_id=instance_nqn(event.instance_uuid),
        )
        logger.debug("Created connector: %s", connector)
        return connector
    except ConflictException:
        logger.info("Connector already exists.")


def instance_nqn(instance_id: UUID):
    return f"nqn.2014-08.org.nvmexpress:uuid:{instance_id}"
