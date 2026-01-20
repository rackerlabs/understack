"""Nautobot device synchronization from Ironic.

This module provides a simple, robust sync function that:
1. Takes just a node_uuid
2. Fetches current state from Ironic (node API + inventory API)
3. Syncs everything to Nautobot (create or update)

Can be called from any event handler - provision, inspect, CRUD, etc.
"""

import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from uuid import UUID

from ironicclient.common.apiclient import exceptions as ironic_exceptions
from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.ironic.provision_state_mapper import ProvisionStateMapper
from understack_workflows.oslo_event.nautobot_device_interface_sync import (
    sync_interfaces_from_data,
)

logger = setup_logger(__name__)

EXIT_STATUS_SUCCESS = 0
EXIT_STATUS_FAILURE = 1


@dataclass
class DeviceInfo:
    """Complete device information synced to Nautobot.

    Populated from Ironic node API and inventory API.
    """

    uuid: str

    # Identity
    name: str | None = None
    serial_number: str | None = None
    service_tag: str | None = None

    # Hardware
    manufacturer: str | None = None
    model: str | None = None

    # Specs (from properties)
    memory_mb: int | None = None
    cpus: int | None = None
    cpu_arch: str | None = None
    local_gb: int | None = None

    # Classification
    traits: list[str] = field(default_factory=list)

    # Location
    location_id: str | None = None
    rack_id: str | None = None

    # Status
    status: str | None = None

    # Role
    role: str = "server"

    tenant_id: str | None = None

    # Custom fields for Nautobot
    custom_fields: dict[str, str] = field(default_factory=dict)


class RackLocationError(Exception):
    """Raised when node rack location cannot be determined."""

    pass


def _normalise_manufacturer(name: str) -> str:
    """Return a standard name for Manufacturer."""
    if "DELL" in name.upper():
        return "Dell"
    elif "HP" in name.upper():
        return "HP"
    raise ValueError(f"Server manufacturer {name} not supported")


def _populate_from_node(device_info: DeviceInfo, node) -> None:
    """Populate device info from Ironic node object."""
    props = node.properties or {}

    # Hardware specs
    if props.get("memory_mb"):
        device_info.memory_mb = int(props["memory_mb"])
    if props.get("cpus"):
        device_info.cpus = int(props["cpus"])
    device_info.cpu_arch = props.get("cpu_arch")
    if props.get("local_gb"):
        device_info.local_gb = int(props["local_gb"])

    # Traits
    if hasattr(node, "traits") and node.traits:
        device_info.traits = list(node.traits)

    # Provision state -> Nautobot status
    device_info.status = ProvisionStateMapper.translate_to_nautobot(
        node.provision_state
    )

    lessee = node.lessee
    # Convert lessee to string UUID if present
    if lessee:
        try:
            device_info.tenant_id = (
                str(UUID(lessee)) if isinstance(lessee, str) else str(lessee)
            )
        except (ValueError, TypeError) as e:
            logger.warning("Invalid lessee UUID %s: %s", lessee, e)


def _populate_from_inventory(device_info: DeviceInfo, inventory: dict | None) -> None:
    """Populate device info from Ironic inventory."""
    if not inventory:
        return

    inv = inventory.get("inventory", {})
    system_vendor = inv.get("system_vendor", {})

    # Manufacturer from inventory
    vendor = system_vendor.get("manufacturer")
    if vendor:
        device_info.manufacturer = _normalise_manufacturer(vendor)

    # Model - extract base model name, strip SKU/extra info in parentheses
    # e.g., "PowerEdge R7615 (SKU=0AF7;ModelName=PowerEdge R7615)" -> "PowerEdge R7615"
    # Uses same regex as ironic_understack/inspect_hook_chassis_model.py
    product_name = system_vendor.get("product_name")
    if product_name and product_name != "System":
        device_info.model = re.sub(r" \(.*\)", "", str(product_name))

    # Service tag: sku (REDFISH) or serial_number (AGENT)
    service_tag = system_vendor.get("sku") or system_vendor.get("serial_number")
    if service_tag:
        device_info.service_tag = service_tag

    # Serial number: only if sku exists (REDFISH has both)
    if system_vendor.get("sku"):
        device_info.serial_number = system_vendor.get("serial_number")


def _generate_device_name(device_info: DeviceInfo) -> None:
    """Generate device name from manufacturer and service tag."""
    if device_info.manufacturer and device_info.service_tag:
        device_info.name = f"{device_info.manufacturer}-{device_info.service_tag}"


def _set_location_from_switches(
    device_info: DeviceInfo,
    ports: list,
    nautobot_client: Nautobot,
) -> None:
    """Determine device location from connected switches.

    Args:
        device_info: DeviceInfo to update with location
        ports: Pre-fetched list of Ironic port objects
        nautobot_client: Nautobot API client
    """
    try:
        locations = set()

        for port in ports:
            llc = port.local_link_connection or {}
            switch_info = llc.get("switch_info")

            # Skip if switch_info is missing, empty, or placeholder "None" string
            if not switch_info or switch_info == "None":
                continue

            # Find switch in Nautobot by name
            device = nautobot_client.dcim.devices.get(name=switch_info)

            if (
                device
                and not isinstance(device, list)
                and device.location
                and device.rack
            ):
                locations.add((device.location.id, device.rack.id))

        if not locations:
            logger.warning("No switch locations found for node %s", device_info.uuid)
            return

        if len(locations) > 1:
            logger.warning(
                "Node %s connected to switches in multiple racks: %s",
                device_info.uuid,
                locations,
            )

        # Use first location found
        location_id, rack_id = next(iter(locations))
        device_info.location_id = location_id
        device_info.rack_id = rack_id

    except Exception as e:
        logger.error(
            "Failed to determine location for node %s: %s", device_info.uuid, e
        )


def fetch_device_info(
    node_uuid: str,
    ironic_client: IronicClient,
    nautobot_client: Nautobot,
) -> tuple[DeviceInfo, dict, list]:
    """Fetch complete device info from Ironic.

    Args:
        node_uuid: Ironic node UUID
        ironic_client: Ironic API client
        nautobot_client: Nautobot API client (for switch location lookup)

    Returns:
        Tuple of (DeviceInfo, inventory dict, ports list)
    """
    device_info = DeviceInfo(uuid=node_uuid)

    node = ironic_client.get_node(node_uuid)

    # Inventory may not exist yet for newly created nodes (pre-inspection)
    try:
        inventory = ironic_client.get_node_inventory(node_ident=node_uuid)
    except ironic_exceptions.NotFound:
        logger.info("No inventory yet for node %s (not inspected)", node_uuid)
        inventory = {}

    ports = ironic_client.list_ports(node_id=node_uuid)

    # Populate in order
    _populate_from_node(device_info, node)
    _populate_from_inventory(device_info, inventory)
    _generate_device_name(device_info)
    _set_location_from_switches(device_info, ports, nautobot_client)

    return device_info, inventory, ports


def _create_nautobot_device(device_info: DeviceInfo, nautobot_client: Nautobot):
    """Create a new device in Nautobot with minimal required fields.

    Returns the created device object for subsequent updates.
    """
    if not device_info.location_id:
        raise ValueError(f"Cannot create device {device_info.uuid} without location")

    # Only mandatory fields for creation
    device_attrs = {
        "id": device_info.uuid,
        "name": device_info.name or device_info.uuid,  # Fallback to UUID if no name
        "status": "Planned",  # Default status, will be updated
        "role": {"name": device_info.role},
        "device_type": {
            "manufacturer": {"name": device_info.manufacturer},
            "model": device_info.model,
        },
        "location": device_info.location_id,
    }

    nautobot_device = nautobot_client.dcim.devices.create(**device_attrs)
    logger.info("Created device %s in Nautobot", device_info.uuid)
    return nautobot_device


def _get_record_value(record, attr: str = "value") -> str | None:
    """Extract value from pynautobot Record object.

    pynautobot returns Record objects for choice fields (status, etc.)
    and related objects (location, rack, tenant). This helper extracts
    the comparable value.

    Args:
        record: pynautobot Record object or primitive value
        attr: Attribute to extract ("value" for choices, "id" for relations)

    Returns:
        String value or None
    """
    if record is None:
        return None
    if hasattr(record, attr):
        return getattr(record, attr)
    # Already a primitive value
    return str(record) if record else None


def _update_nautobot_device(
    device_info: DeviceInfo,
    nautobot_device,
) -> bool:
    """Update existing Nautobot device with current info.

    Returns True if any changes were made.
    """
    updated = False

    # Status (Record with .name for display name e.g., "Staged", "Active")
    # ProvisionStateMapper returns display names like "Staged", "Active"
    if device_info.status:
        current_status = _get_record_value(nautobot_device.status, "name")
        if current_status != device_info.status:
            nautobot_device.status = device_info.status
            updated = True
            logger.debug(
                "Updating status: %s -> %s", current_status, device_info.status
            )

    # Name (can change on chassis swap)
    if device_info.name and nautobot_device.name != device_info.name:
        nautobot_device.name = device_info.name
        updated = True
        logger.debug("Updating name: %s", device_info.name)

    # Serial number (can change on chassis swap)
    if (
        device_info.serial_number
        and nautobot_device.serial != device_info.serial_number
    ):
        nautobot_device.serial = device_info.serial_number
        updated = True
        logger.debug("Updating serial: %s", device_info.serial_number)

    # Location (Record with .id attribute)
    if device_info.location_id:
        current_location = _get_record_value(nautobot_device.location, "id")
        if current_location != device_info.location_id:
            nautobot_device.location = device_info.location_id
            updated = True
            logger.debug("Updating location: %s", device_info.location_id)

    # Rack (Record with .id attribute)
    if device_info.rack_id:
        current_rack = _get_record_value(nautobot_device.rack, "id")
        if current_rack != device_info.rack_id:
            nautobot_device.rack = device_info.rack_id
            updated = True
            logger.debug("Updating rack: %s", device_info.rack_id)

    # Tenant (Record with .id attribute, from Ironic lessee)
    if device_info.tenant_id:
        current_tenant = _get_record_value(nautobot_device.tenant, "id")
        if current_tenant != str(device_info.tenant_id):
            nautobot_device.tenant = str(device_info.tenant_id)
            updated = True
            logger.debug("Updating tenant: %s", device_info.tenant_id)

    # Custom fields (merge, don't replace)
    # pynautobot tracks custom_fields specially - we need to modify in place
    cf_updated = False
    if device_info.custom_fields:
        current_cf = (
            dict(nautobot_device.custom_fields) if nautobot_device.custom_fields else {}
        )
        for key, value in device_info.custom_fields.items():
            if current_cf.get(key) != value:
                current_cf[key] = value
                cf_updated = True
                logger.debug("Updating custom field %s: %s", key, value)
        if cf_updated:
            nautobot_device.custom_fields = current_cf
            updated = True

    if updated:
        result = nautobot_device.save()
        logger.info(
            "Updated device %s in Nautobot, save result: %s", device_info.uuid, result
        )
    else:
        logger.debug("No changes for device %s", device_info.uuid)

    return updated


def sync_device_to_nautobot(
    node_uuid: str,
    nautobot_client: Nautobot,
    sync_interfaces: bool = True,
) -> int:
    """Sync an Ironic node to Nautobot.

    This is the main entry point. It:
    1. Fetches current state from Ironic (node + inventory + ports)
    2. Creates or updates the device in Nautobot
    3. Optionally syncs interfaces (ports) to Nautobot

    Can be called from any event handler.

    Args:
        node_uuid: Ironic node UUID
        nautobot_client: Nautobot API client
        sync_interfaces: Whether to also sync interfaces (default: True)

    Returns:
        EXIT_STATUS_SUCCESS on success, EXIT_STATUS_FAILURE on failure
    """
    if not node_uuid:
        logger.error("Missing node UUID")
        return EXIT_STATUS_FAILURE

    try:
        ironic_client = IronicClient()

        # Fetch all device info from Ironic (returns inventory and ports too)
        device_info, inventory, ports = fetch_device_info(
            node_uuid, ironic_client, nautobot_client
        )

        # Check if device exists in Nautobot
        nautobot_device = nautobot_client.dcim.devices.get(id=device_info.uuid)

        if not nautobot_device:
            # Try finding by name (handles re-enrollment scenarios)
            if device_info.name:
                nautobot_device = nautobot_client.dcim.devices.get(
                    name=device_info.name
                )
                if nautobot_device and not isinstance(nautobot_device, list):
                    logger.info(
                        "Found existing device by name %s with ID %s, "
                        "will recreate with UUID %s",
                        device_info.name,
                        nautobot_device.id,
                        device_info.uuid,
                    )
                    if str(nautobot_device.id) != device_info.uuid:
                        logger.warning(
                            "Device %s has mismatched UUID (Nautobot: %s, Ironic: %s), "
                            "recreating",
                            device_info.name,
                            nautobot_device.id,
                            device_info.uuid,
                        )
                        nautobot_device.delete()
                        nautobot_device = None  # Will trigger creation below

        if not nautobot_device:
            # Skip sync for uninspected nodes - no location means we can't create
            # the device yet. The inspection event will trigger sync with full data.
            if not device_info.location_id:
                logger.info(
                    "Skipping sync for node %s - no location yet (awaiting inspection)",
                    node_uuid,
                )
                return EXIT_STATUS_FAILURE
            nautobot_device = _create_nautobot_device(device_info, nautobot_client)

        # Update device with all fields (works for both new and existing)
        _update_nautobot_device(device_info, nautobot_device)

        # Sync interfaces using already-fetched inventory and ports
        if sync_interfaces:
            interface_result = sync_interfaces_from_data(
                node_uuid, inventory, ports, nautobot_client
            )
            if interface_result != EXIT_STATUS_SUCCESS:
                logger.warning(
                    "Interface sync failed for node %s, device sync succeeded",
                    node_uuid,
                )
                # Don't fail the whole operation if interface sync fails
                # Device is already synced successfully

        return EXIT_STATUS_SUCCESS

    except Exception:
        logger.exception("Failed to sync device %s to Nautobot", node_uuid)
        return EXIT_STATUS_FAILURE


def _extract_node_uuid_from_event(event_data: dict[str, Any]) -> str | None:
    """Extract node UUID from any Ironic node event payload.

    Supports:
    - NodeSetProvisionStatePayload (provision_set events)
    - NodeCRUDPayload (create/update/delete events)
    - NodeSetPowerStatePayload (power_set events)
    - NodeCorrectedPowerStatePayload (power_state_corrected events)
    - NodePayload (maintenance events)

    All these payloads have 'uuid' in ironic_object.data or at top level.
    """
    # Try payload.ironic_object.data.uuid first (standard notification format)
    payload = event_data.get("payload", {})
    if isinstance(payload, dict):
        ironic_data = payload.get("ironic_object.data", {})
        if isinstance(ironic_data, dict) and ironic_data.get("uuid"):
            return ironic_data["uuid"]

    # Try ironic_object.uuid at top level (some event formats)
    ironic_object = event_data.get("ironic_object", {})
    if isinstance(ironic_object, dict) and ironic_object.get("uuid"):
        return ironic_object["uuid"]

    return None


def handle_node_event(
    _conn: Connection, nautobot_client: Nautobot, event_data: dict[str, Any]
) -> int:
    """Handle any Ironic node event and sync to Nautobot.

    This is a generic handler that works with:
    - baremetal.node.provision_set.end
    - baremetal.node.update.end
    - baremetal.node.power_set.end
    - baremetal.node.power_state_corrected.success
    - baremetal.node.maintenance_set.end

    Args:
        _conn: OpenStack connection (unused, kept for handler signature)
        nautobot_client: Nautobot API client
        event_data: Raw event data dict

    Returns:
        EXIT_STATUS_SUCCESS on success, EXIT_STATUS_FAILURE on failure
    """
    node_uuid = _extract_node_uuid_from_event(event_data)
    if not node_uuid:
        logger.error("Could not extract node UUID from event: %s", event_data)
        return EXIT_STATUS_FAILURE

    event_type = event_data.get("event_type", "unknown")
    logger.info("Handling %s for node %s", event_type, node_uuid)

    return sync_device_to_nautobot(node_uuid, nautobot_client)


def delete_device_from_nautobot(node_uuid: str, nautobot_client: Nautobot) -> int:
    """Delete a device from Nautobot.

    Args:
        node_uuid: Ironic node UUID (used as device ID in Nautobot)
        nautobot_client: Nautobot API client

    Returns:
        EXIT_STATUS_SUCCESS on success, EXIT_STATUS_FAILURE on failure
    """
    if not node_uuid:
        logger.error("Missing node UUID for delete")
        return EXIT_STATUS_FAILURE

    try:
        nautobot_device = nautobot_client.dcim.devices.get(id=node_uuid)

        if not nautobot_device or isinstance(nautobot_device, list):
            logger.info("Device %s not found in Nautobot, nothing to delete", node_uuid)
            return EXIT_STATUS_SUCCESS

        nautobot_device.delete()
        logger.info("Deleted device %s from Nautobot", node_uuid)
        return EXIT_STATUS_SUCCESS

    except Exception:
        logger.exception("Failed to delete device %s from Nautobot", node_uuid)
        return EXIT_STATUS_FAILURE


def handle_node_delete_event(
    _conn: Connection, nautobot_client: Nautobot, event_data: dict[str, Any]
) -> int:
    """Handle Ironic node delete event and remove from Nautobot.

    Args:
        _conn: OpenStack connection (unused, kept for handler signature)
        nautobot_client: Nautobot API client
        event_data: Raw event data dict

    Returns:
        EXIT_STATUS_SUCCESS on success, EXIT_STATUS_FAILURE on failure
    """
    node_uuid = _extract_node_uuid_from_event(event_data)
    if not node_uuid:
        logger.error("Could not extract node UUID from delete event: %s", event_data)
        return EXIT_STATUS_FAILURE

    logger.info("Handling node delete for %s", node_uuid)
    return delete_device_from_nautobot(node_uuid, nautobot_client)
