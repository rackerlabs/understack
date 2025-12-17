"""Nautobot device interface synchronization from Ironic.

This module syncs interfaces from Ironic node inventory to Nautobot.
It:
1. Fetches node inventory from Ironic (contains interface list with MACs)
2. Fetches ports from Ironic (contains port UUIDs and local_link_connection)
3. Creates/updates interfaces in Nautobot with matching UUIDs
4. Creates/updates iDRAC management interface from inventory bmc_mac

The Ironic port UUID is used as the Nautobot interface ID to maintain
consistency between the two systems. For iDRAC interfaces, a deterministic
UUID is generated from the device UUID and MAC address.
"""

from dataclasses import dataclass
from dataclasses import field
from typing import Any

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient

logger = setup_logger(__name__)

# Interface type mapping based on NIC naming conventions
INTERFACE_TYPE_MAP = {
    "slot": "25gbase-x-sfp28",  # PCIe slot NICs typically 25GbE
    "embedded": "25gbase-x-sfp28",  # Embedded NICs
    "integrated": "25gbase-x-sfp28",  # Integrated NICs
}
DEFAULT_INTERFACE_TYPE = "25gbase-x-sfp28"


@dataclass
class InterfaceInfo:
    """Interface information to sync to Nautobot."""

    uuid: str  # Ironic port UUID, used as Nautobot interface ID
    name: str  # Interface name (e.g., NIC.Slot.1-1)
    mac_address: str
    device_uuid: str  # Node UUID
    description: str = ""
    interface_type: str = DEFAULT_INTERFACE_TYPE
    enabled: bool = True
    mgmt_only: bool = False
    pxe_enabled: bool = False

    # Local link connection info (for cable management)
    switch_port_id: str | None = None
    switch_info: str | None = None
    switch_id: str | None = None
    physical_network: str | None = None


@dataclass
class DeviceInterfacesInfo:
    """All interfaces for a device."""

    device_uuid: str
    interfaces: list[InterfaceInfo] = field(default_factory=list)


def _get_interface_type(name: str) -> str:
    """Determine interface type based on name."""
    name_lower = name.lower()
    for key, iface_type in INTERFACE_TYPE_MAP.items():
        if key in name_lower:
            return iface_type
    return DEFAULT_INTERFACE_TYPE


def _get_interface_description(name: str) -> str:
    """Generate human-readable description from interface name.

    Examples:
        NIC.Embedded.1-1-1 -> "Embedded NIC 1 Port 1 Partition 1"
        NIC.Embedded.2-1-1 -> "Embedded NIC 2 Port 1 Partition 1"
        NIC.Integrated.1-1 -> "Integrated NIC 1 Port 1"
        NIC.Integrated.1-2 -> "Integrated NIC 1 Port 2"
        NIC.Slot.1-1 -> "NIC in Slot 1 Port 1"
        NIC.Slot.1-2 -> "NIC in Slot 1 Port 2"
    """
    name_lower = name.lower()

    if "idrac" in name_lower:
        return "Dedicated iDRAC interface"

    # Extract the suffix part (e.g., "1-1-1", "2-1-1", "1-1", "1-2")
    parts = name.split(".")
    if len(parts) < 3:
        return ""

    suffix = parts[2]  # e.g., "1-1-1" or "1-2"
    suffix_parts = suffix.split("-")

    if "embedded" in name_lower:
        # NIC.Embedded.X-Y-Z -> Embedded NIC X Port Y Partition Z
        if len(suffix_parts) >= 3:
            nic, port, part = suffix_parts[0], suffix_parts[1], suffix_parts[2]
            return f"Embedded NIC {nic} Port {port} Partition {part}"
        elif len(suffix_parts) >= 2:
            return f"Embedded NIC {suffix_parts[0]} Port {suffix_parts[1]}"

    if "integrated" in name_lower:
        # NIC.Integrated.X-Y -> Integrated NIC X Port Y
        if len(suffix_parts) >= 2:
            return f"Integrated NIC {suffix_parts[0]} Port {suffix_parts[1]}"

    if "slot" in name_lower:
        # NIC.Slot.X-Y -> NIC in Slot X Port Y
        if len(suffix_parts) >= 2:
            return f"NIC in Slot {suffix_parts[0]} Port {suffix_parts[1]}"

    return ""


def _build_interface_map_from_inventory(inventory: dict) -> dict[str, dict]:
    """Build a map of MAC address -> interface info from inventory.

    Args:
        inventory: Ironic node inventory dict

    Returns:
        Dict mapping MAC address (lowercase) to interface details
    """
    interface_map = {}
    inv = inventory.get("inventory", {})

    for iface in inv.get("interfaces", []):
        mac = iface.get("mac_address", "").lower()
        if mac:
            interface_map[mac] = {
                "name": iface.get("name", ""),
            }

    return interface_map


def _assign_ip_to_interface(
    nautobot_client: Nautobot,
    interface_id: str,
    ip_address: str,
) -> None:
    """Assign an IP address to an interface in Nautobot.

    Creates the IP address if it doesn't exist, then associates it with
    the interface.

    Args:
        nautobot_client: Nautobot API client
        interface_id: Nautobot interface ID
        ip_address: IP address string (e.g., "10.46.96.157")
    """
    if not ip_address:
        return

    # Check if IP already exists
    existing_ip = nautobot_client.ipam.ip_addresses.get(address=ip_address)

    if existing_ip and not isinstance(existing_ip, list) and hasattr(existing_ip, "id"):
        ip_id = existing_ip.id  # type: ignore[union-attr]
        logger.debug("IP address %s already exists: %s", ip_address, ip_id)
    else:
        # Create new IP address
        # Note: We don't specify parent prefix - Nautobot will auto-assign
        # based on existing prefixes if configured
        try:
            new_ip = nautobot_client.ipam.ip_addresses.create(
                address=ip_address,
                status="Active",
            )
            ip_id = getattr(new_ip, "id", None)
            if not ip_id:
                logger.warning("Failed to get ID for created IP address %s", ip_address)
                return
            logger.info("Created IP address %s: %s", ip_address, ip_id)
        except Exception as e:
            logger.warning("Failed to create IP address %s: %s", ip_address, e)
            return

    # Check if IP is already associated with this interface
    existing_assoc = nautobot_client.ipam.ip_address_to_interface.get(ip_address=ip_id)

    if existing_assoc and not isinstance(existing_assoc, list):
        assoc_interface = getattr(existing_assoc, "interface", None)
        assoc_interface_id = (
            getattr(assoc_interface, "id", None) if assoc_interface else None
        )
        if assoc_interface_id == interface_id:
            logger.debug(
                "IP %s already associated with interface %s", ip_address, interface_id
            )
            return
        else:
            # IP is associated with a different interface
            logger.warning(
                "IP %s is already associated with interface %s, not %s",
                ip_address,
                assoc_interface_id,
                interface_id,
            )
            return

    # Associate IP with interface
    try:
        nautobot_client.ipam.ip_address_to_interface.create(
            ip_address=ip_id,
            interface=interface_id,
            is_primary=True,
        )
        logger.info("Associated IP %s with interface %s", ip_address, interface_id)
    except Exception as e:
        logger.warning("Failed to associate IP %s with interface: %s", ip_address, e)


def sync_idrac_interface(
    device_uuid: str,
    bmc_mac: str,
    nautobot_client: Nautobot,
    bmc_ip: str | None = None,
) -> None:
    """Sync iDRAC interface to Nautobot.

    Creates or updates the iDRAC management interface for a device.
    Looks up existing interface by name + device_id.
    Optionally assigns the BMC IP address to the interface.

    TODO: Add cable management for iDRAC. Currently not implemented because
    LLDP data for iDRAC switch connection is not available in Ironic inventory.
    Would require querying the BMC directly via Redfish (see bmc_chassis_info.py).

    Args:
        device_uuid: Nautobot device UUID
        bmc_mac: BMC MAC address from inventory
        nautobot_client: Nautobot API client
        bmc_ip: Optional BMC IP address from inventory (bmc_address)
    """
    if not bmc_mac:
        logger.debug("No bmc_mac provided for device %s", device_uuid)
        return

    mac_address = bmc_mac.upper()
    idrac_interface = None

    # Check if iDRAC interface already exists
    existing = nautobot_client.dcim.interfaces.get(
        device_id=device_uuid,
        name="iDRAC",
    )

    # pynautobot.get() can return Record, list, or None - we expect a single Record
    if existing and not isinstance(existing, list):
        # Update if MAC changed
        current_mac = getattr(existing, "mac_address", None)
        if current_mac and hasattr(current_mac, "upper"):
            current_mac = current_mac.upper()

        if current_mac != mac_address:
            existing.mac_address = mac_address  # type: ignore[attr-defined]
            existing.save()  # type: ignore[union-attr]
            logger.info("Updated iDRAC MAC for device %s: %s", device_uuid, mac_address)
        else:
            logger.debug(
                "iDRAC interface already up to date for device %s", device_uuid
            )
        idrac_interface = existing
    else:
        # Create new iDRAC interface
        idrac_interface = nautobot_client.dcim.interfaces.create(
            device=device_uuid,
            name="iDRAC",
            type="1000base-t",
            mac_address=mac_address,
            description="Dedicated iDRAC interface",
            mgmt_only=True,
            enabled=True,
            status="Active",
        )
        logger.info(
            "Created iDRAC interface for device %s: %s", device_uuid, mac_address
        )

    # Assign BMC IP address to iDRAC interface
    if idrac_interface and bmc_ip:
        idrac_id = getattr(idrac_interface, "id", None)
        if idrac_id:
            _assign_ip_to_interface(nautobot_client, idrac_id, bmc_ip)


def _build_interfaces_from_ports(
    node_uuid: str,
    ports: list,
    inventory_map: dict[str, dict],
) -> list[InterfaceInfo]:
    """Build InterfaceInfo list from Ironic ports and inventory.

    Args:
        node_uuid: Ironic node UUID
        ports: List of Ironic port objects
        inventory_map: MAC -> interface info from inventory

    Returns:
        List of InterfaceInfo objects
    """
    interfaces = []

    for port in ports:
        mac = port.address.lower() if port.address else ""
        extra = port.extra or {}
        llc = port.local_link_connection or {}

        # Get interface name: prefer bios_name from extra, then inventory,
        # then port name
        bios_name = extra.get("bios_name")
        inv_info = inventory_map.get(mac, {})
        inv_name = inv_info.get("name", "")

        # Priority: bios_name > inventory name > port name > port UUID
        name = bios_name or inv_name or port.name or port.uuid

        interface = InterfaceInfo(
            uuid=port.uuid,
            name=name,
            mac_address=mac.upper(),  # Nautobot expects uppercase MACs
            device_uuid=node_uuid,
            description=_get_interface_description(name),
            interface_type=_get_interface_type(name),
            pxe_enabled=port.pxe_enabled or False,
            switch_port_id=llc.get("port_id"),
            switch_info=llc.get("switch_info"),
            switch_id=llc.get("switch_id"),
            physical_network=port.physical_network,
        )
        interfaces.append(interface)

    return interfaces


def fetch_device_interfaces(
    node_uuid: str,
    ironic_client: IronicClient,
) -> tuple[DeviceInterfacesInfo, dict]:
    """Fetch all interface info for a device from Ironic.

    Args:
        node_uuid: Ironic node UUID
        ironic_client: Ironic API client

    Returns:
        Tuple of (DeviceInterfacesInfo with all interfaces, inventory dict)
    """
    result = DeviceInterfacesInfo(device_uuid=node_uuid)

    # Fetch inventory for interface names
    try:
        inventory = ironic_client.get_node_inventory(node_ident=node_uuid)
    except Exception as e:
        logger.warning("Could not fetch inventory for node %s: %s", node_uuid, e)
        inventory = {}

    # Build MAC -> interface info map from inventory
    inventory_map = _build_interface_map_from_inventory(inventory)

    # Fetch ports (these have the UUIDs we need)
    ports = ironic_client.list_ports(node_id=node_uuid)

    # Build interface list
    result.interfaces = _build_interfaces_from_ports(node_uuid, ports, inventory_map)

    logger.info("Fetched %d interfaces for node %s", len(result.interfaces), node_uuid)
    return result, inventory


def _get_record_value(record, attr: str = "value") -> str | None:
    """Extract value from pynautobot Record object."""
    if record is None:
        return None
    if hasattr(record, attr):
        return getattr(record, attr)
    return str(record) if record else None


def _create_nautobot_interface(
    interface: InterfaceInfo,
    nautobot_client: Nautobot,
):
    """Create a new interface in Nautobot."""
    attrs = {
        "id": interface.uuid,
        "name": interface.name,
        "type": interface.interface_type,
        "status": "Active",
        "mac_address": interface.mac_address,
        "device": interface.device_uuid,
        "enabled": interface.enabled,
        "mgmt_only": interface.mgmt_only,
    }

    if interface.description:
        attrs["description"] = interface.description

    try:
        nautobot_intf = nautobot_client.dcim.interfaces.create(**attrs)
        logger.info(
            "Created interface %s (%s) in Nautobot", interface.name, interface.uuid
        )
        return nautobot_intf
    except Exception as e:
        # Handle race condition - interface may already exist
        if "unique" in str(e).lower():
            logger.info("Interface %s already exists, fetching", interface.uuid)
            return nautobot_client.dcim.interfaces.get(id=interface.uuid)
        raise


def _delete_nautobot_interface(nautobot_intf, nautobot_client: Nautobot) -> None:
    """Delete an interface and its associated cable from Nautobot."""
    intf_id = nautobot_intf.id

    # Delete cable first if exists
    if nautobot_intf.cable:
        try:
            nautobot_intf.cable.delete()
            logger.debug("Deleted cable for interface %s", intf_id)
        except Exception as e:
            logger.warning("Failed to delete cable for interface %s: %s", intf_id, e)

    # Delete the interface
    nautobot_intf.delete()
    logger.info("Deleted interface %s from Nautobot", intf_id)


def _update_nautobot_interface(
    interface: InterfaceInfo,
    nautobot_intf,
    nautobot_client: Nautobot,
):
    """Update existing Nautobot interface.

    If there's a name conflict with another interface on the same device,
    deletes the conflicting interface first, then updates this one.

    Returns the updated interface object.
    """
    updated = False

    # Name - if different, check for conflicts
    if interface.name and nautobot_intf.name != interface.name:
        # Check if another interface with this name already exists on the device
        existing = nautobot_client.dcim.interfaces.get(
            device_id=interface.device_uuid,
            name=interface.name,
        )
        if (
            existing
            and not isinstance(existing, list)
            and existing.id != interface.uuid
        ):
            # Delete the conflicting interface and recreate with fresh data
            logger.info(
                "Name conflict: deleting interface %s ('%s') to update %s",
                existing.id,
                interface.name,
                interface.uuid,
            )
            _delete_nautobot_interface(existing, nautobot_client)

        nautobot_intf.name = interface.name
        updated = True
        logger.debug("Updating interface name: %s", interface.name)

    # MAC address
    current_mac = _get_record_value(nautobot_intf.mac_address)
    if interface.mac_address and current_mac != interface.mac_address:
        nautobot_intf.mac_address = interface.mac_address
        updated = True
        logger.debug("Updating interface MAC: %s", interface.mac_address)

    # Type
    current_type = _get_record_value(nautobot_intf.type, "value")
    if interface.interface_type and current_type != interface.interface_type:
        nautobot_intf.type = interface.interface_type
        updated = True
        logger.debug("Updating interface type: %s", interface.interface_type)

    # Description
    if interface.description and nautobot_intf.description != interface.description:
        nautobot_intf.description = interface.description
        updated = True
        logger.debug("Updating interface description: %s", interface.description)

    # Management only flag (important for iDRAC interfaces)
    if nautobot_intf.mgmt_only != interface.mgmt_only:
        nautobot_intf.mgmt_only = interface.mgmt_only
        updated = True
        logger.debug("Updating interface mgmt_only: %s", interface.mgmt_only)

    if updated:
        nautobot_intf.save()
        logger.info("Updated interface %s in Nautobot", interface.uuid)

    return nautobot_intf


def _handle_cable_management(
    interface: InterfaceInfo,
    nautobot_intf,
    nautobot_client: Nautobot,
) -> None:
    """Handle cable creation/update for interface with switch connection info."""
    if not interface.switch_info or not interface.switch_port_id:
        return

    logger.debug(
        "Handling cable for interface %s -> %s:%s",
        interface.uuid,
        interface.switch_info,
        interface.switch_port_id,
    )

    # Find the switch interface
    switch_intf = nautobot_client.dcim.interfaces.get(
        device=interface.switch_info,
        name=interface.switch_port_id,
    )
    if not switch_intf or isinstance(switch_intf, list):
        logger.warning(
            "Switch interface %s not found on device %s",
            interface.switch_port_id,
            interface.switch_info,
        )
        return

    switch_intf_id = switch_intf.id

    # Check if cable already exists
    if nautobot_intf.cable:
        cable = nautobot_intf.cable
        # Verify cable connects to correct switch port
        if (
            cable.termination_a_id == interface.uuid
            and cable.termination_b_id == switch_intf_id
        ) or (
            cable.termination_b_id == interface.uuid
            and cable.termination_a_id == switch_intf_id
        ):
            logger.debug(
                "Cable already exists correctly for interface %s", interface.uuid
            )
            return

        # Update cable to correct endpoints
        cable.termination_a_id = interface.uuid
        cable.termination_a_type = "dcim.interface"
        cable.termination_b_id = switch_intf_id
        cable.termination_b_type = "dcim.interface"
        cable.status = "Connected"
        cable.save()
        logger.info("Updated cable for interface %s", interface.uuid)
    else:
        # Create new cable
        try:
            nautobot_client.dcim.cables.create(
                termination_a_type="dcim.interface",
                termination_a_id=interface.uuid,
                termination_b_type="dcim.interface",
                termination_b_id=switch_intf_id,
                status="Connected",
            )
            logger.info(
                "Created cable connecting %s to %s:%s",
                interface.uuid,
                interface.switch_info,
                interface.switch_port_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to create cable for interface %s: %s", interface.uuid, e
            )


def sync_interfaces_from_data(
    node_uuid: str,
    inventory: dict,
    ports: list,
    nautobot_client: Nautobot,
) -> int:
    """Sync interfaces to Nautobot using pre-fetched inventory and ports.

    Use this when you already have inventory and ports data (e.g., from
    nautobot_device_sync) to avoid duplicate API calls.

    Args:
        node_uuid: Ironic node UUID
        inventory: Ironic node inventory dict (from get_node_inventory)
        ports: List of Ironic port objects (from list_ports)
        nautobot_client: Nautobot API client

    Returns:
        0 on success, 1 on failure
    """
    if not node_uuid:
        logger.error("Missing node UUID")
        return 1

    try:
        # Build MAC -> interface info map from inventory
        inventory_map = _build_interface_map_from_inventory(inventory)

        # Build interface list from ports and inventory
        interfaces = _build_interfaces_from_ports(node_uuid, ports, inventory_map)

        # Sync each interface
        for interface in interfaces:
            nautobot_intf = nautobot_client.dcim.interfaces.get(id=interface.uuid)

            if not nautobot_intf:
                nautobot_intf = _create_nautobot_interface(interface, nautobot_client)
            else:
                _update_nautobot_interface(interface, nautobot_intf, nautobot_client)

            # Handle cable management
            if nautobot_intf:
                _handle_cable_management(interface, nautobot_intf, nautobot_client)

        # Sync iDRAC interface separately (not part of Ironic ports)
        inv = inventory.get("inventory", {})
        bmc_mac = inv.get("bmc_mac")
        bmc_ip = inv.get("bmc_address")
        if bmc_mac:
            sync_idrac_interface(node_uuid, bmc_mac, nautobot_client, bmc_ip)

        logger.info(
            "Synced %d interfaces for node %s to Nautobot",
            len(interfaces),
            node_uuid,
        )
        return 0

    except Exception:
        logger.exception("Failed to sync interfaces for node %s to Nautobot", node_uuid)
        return 1


def sync_interfaces_to_nautobot(
    node_uuid: str,
    nautobot_client: Nautobot,
    ironic_client: IronicClient | None = None,
) -> int:
    """Sync all interfaces for an Ironic node to Nautobot.

    This fetches inventory and ports from Ironic, then syncs to Nautobot.
    If you already have inventory and ports data, use sync_interfaces_from_data()
    instead to avoid duplicate API calls.

    Args:
        node_uuid: Ironic node UUID
        nautobot_client: Nautobot API client
        ironic_client: Optional Ironic client (created if not provided)

    Returns:
        0 on success, 1 on failure
    """
    if not node_uuid:
        logger.error("Missing node UUID")
        return 1

    try:
        if ironic_client is None:
            ironic_client = IronicClient()

        # Fetch inventory
        try:
            inventory = ironic_client.get_node_inventory(node_ident=node_uuid)
        except Exception as e:
            logger.warning("Could not fetch inventory for node %s: %s", node_uuid, e)
            inventory = {}

        # Fetch ports
        ports = ironic_client.list_ports(node_id=node_uuid)

        # Delegate to the data-based sync
        return sync_interfaces_from_data(node_uuid, inventory, ports, nautobot_client)

    except Exception:
        logger.exception("Failed to sync interfaces for node %s to Nautobot", node_uuid)
        return 1


def _extract_node_uuid_from_event(event_data: dict[str, Any]) -> str | None:
    """Extract node UUID from Ironic event payload."""
    payload = event_data.get("payload", {})
    if isinstance(payload, dict):
        ironic_data = payload.get("ironic_object.data", {})
        if isinstance(ironic_data, dict):
            # For port events, get node_uuid
            if ironic_data.get("node_uuid"):
                return ironic_data["node_uuid"]
            # For node events, get uuid
            if ironic_data.get("uuid"):
                return ironic_data["uuid"]
    return None


def handle_interface_sync_event(
    _conn: Connection,
    nautobot_client: Nautobot,
    event_data: dict[str, Any],
) -> int:
    """Handle events that should trigger interface sync.

    Works with:
    - baremetal.node.inspect.end (inspection completed, inventory available)
    - baremetal.port.create.end
    - baremetal.port.update.end

    Args:
        _conn: OpenStack connection (unused, kept for handler signature)
        nautobot_client: Nautobot API client
        event_data: Raw event data dict

    Returns:
        0 on success, 1 on failure
    """
    node_uuid = _extract_node_uuid_from_event(event_data)
    if not node_uuid:
        logger.error("Could not extract node UUID from event: %s", event_data)
        return 1

    event_type = event_data.get("event_type", "unknown")
    logger.info("Handling %s - syncing interfaces for node %s", event_type, node_uuid)

    return sync_interfaces_to_nautobot(node_uuid, nautobot_client)
