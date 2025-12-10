from ipaddress import IPv4Interface

from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


def parse_port_to_interface(port_data: dict, hostname: str) -> InterfaceInfo:
    """Parse Ironic port data to InterfaceInfo.

    This is the preferred method as ports have enriched data from inspection hooks:
    - bios_name in extra field (from Redfish inspection)
    - local_link_connection with switch info (from Agent inspection)

    Args:
        port_data: Port dict from Ironic API
        hostname: Node hostname

    Returns:
        InterfaceInfo object with parsed data
    """
    extra = port_data.get("extra", {})
    llc = port_data.get("local_link_connection", {})

    # Prefer bios_name from extra, fall back to port name, then MAC
    interface_name = (
        extra.get("bios_name")
        or port_data.get("name")
        or port_data.get("address", "unknown")
    )

    # Extract switch connection info from local_link_connection
    remote_switch_mac = llc.get("switch_id")
    remote_switch_port = llc.get("port_id")

    return InterfaceInfo(
        name=interface_name,
        description=f"Port {port_data.get('uuid', 'unknown')}",
        mac_address=port_data["address"].upper(),
        hostname=hostname,
        ipv4_address=None,  # Server interfaces don't have IPs
        ipv4_gateway=None,
        dhcp=False,
        remote_switch_mac_address=remote_switch_mac,
        remote_switch_port_name=remote_switch_port,
        remote_switch_data_stale=False,
    )


def parse_interface_data(
    interface_data: dict, hostname: str, manufacturer: str
) -> InterfaceInfo:
    """Parse interface data from Ironic inspection inventory.

    Args:
        interface_data: Interface dict from Ironic inventory
        hostname: Node hostname
        manufacturer: System manufacturer

    Returns:
        InterfaceInfo object with parsed data
    """
    # Get interface name - prefer from interface data directly
    # The name field in inventory is typically the Linux interface name
    interface_name = interface_data.get("name", "unknown")

    # Extract LLDP data if available
    # LLDP data structure varies - it could be a list of TLVs or already parsed
    lldp_data = interface_data.get("lldp", [])
    remote_switch_mac = None
    remote_switch_port = None

    # If lldp_data is a list, try to extract switch info
    if isinstance(lldp_data, list) and lldp_data:
        # LLDP TLVs: type 1 = Chassis ID (switch MAC), type 2 = Port ID
        for item in lldp_data:
            if isinstance(item, list | tuple) and len(item) >= 2:
                tlv_type, tlv_value = item[0], item[1]
                if tlv_type == 1:  # Chassis ID
                    remote_switch_mac = tlv_value
                elif tlv_type == 2:  # Port ID
                    remote_switch_port = tlv_value

    # For server interfaces, ignore IP addresses (only iDRAC should have IP info)
    return InterfaceInfo(
        name=interface_name,
        description=f"{interface_data.get('driver', 'Unknown')} interface",
        mac_address=interface_data["mac_address"].upper(),
        hostname=hostname,
        ipv4_address=None,  # Ignore IP addresses for server interfaces
        ipv4_gateway=None,
        dhcp=False,
        remote_switch_mac_address=remote_switch_mac,
        remote_switch_port_name=remote_switch_port,
        remote_switch_data_stale=False,  # Ironic data is typically fresh
    )


def chassis_info_from_ironic_data(
    inspection_data: dict, ports_data: list[dict] | None = None
) -> ChassisInfo:
    """Build ChassisInfo from Ironic inspection and port data.

    Args:
        inspection_data: Node inventory from Ironic inspection
        ports_data: Optional list of port dicts from Ironic API.
                   If provided, will be used instead of inventory interfaces
                   as ports have enriched data from inspection hooks.

    Returns:
        ChassisInfo object
    """
    inventory = inspection_data["inventory"]

    system_vendor = inventory["system_vendor"]
    memory_info = inventory["memory"]
    hostname = inventory.get("hostname")

    # Validate that bmc_address is present
    if "bmc_address" not in inventory or not inventory["bmc_address"]:
        raise ValueError(
            f"bmc_address is required but not present in inventory for {hostname}"
        )

    try:
        # NOTE: Ironic inspection doesn't provide BMC subnet mask, only IP address.
        # We assume /26 as a fallback. For accurate BMC network config, use
        # bmc_chassis_info.bmc_interface() which queries the BMC's Redfish API
        # directly and gets the actual SubnetMask from IPv4Addresses.
        # This is acceptable here since we're building device info from inspection
        # data, and the BMC interface details aren't critical for device creation.
        bmc_ipv4 = IPv4Interface(f"{inventory['bmc_address']}/26")
    except ValueError:
        bmc_ipv4 = None

    bmc_interface = InterfaceInfo(
        name="iDRAC",
        description="Dedicated iDRAC interface",
        mac_address=inventory["bmc_mac"].upper(),
        hostname=hostname,
        ipv4_address=bmc_ipv4,
        ipv4_gateway=None,
        dhcp=False,
        remote_switch_mac_address=None,
        remote_switch_port_name=None,
        remote_switch_data_stale=False,
    )

    manufacturer = system_vendor["manufacturer"]

    interfaces = [bmc_interface]

    # Prefer port data if available (has enriched data from inspection hooks)
    if ports_data:
        logger.debug("Using %d ports from Ironic API", len(ports_data))
        for port_data in ports_data:
            try:
                interfaces.append(parse_port_to_interface(port_data, hostname))
            except Exception as e:
                logger.warning(
                    "Failed to parse port %s: %s", port_data.get("uuid", "unknown"), e
                )
    else:
        # Fall back to inventory interfaces
        logger.debug("Using %d interfaces from inventory", len(inventory["interfaces"]))
        for interface_data in inventory["interfaces"]:
            interfaces.append(
                parse_interface_data(interface_data, hostname, manufacturer)
            )

    return ChassisInfo(
        manufacturer=manufacturer,
        model_number=system_vendor["product_name"].split("(")[0].strip(),
        serial_number=system_vendor["serial_number"],
        bmc_ip_address=inventory["bmc_address"],
        bios_version=system_vendor["firmware"]["version"],
        power_on=True,  # Assume powered on since inspection is running
        interfaces=interfaces,
        memory_gib=int(memory_info["physical_mb"] / 1024),
        cpu=inventory["cpu"]["model_name"],
    )


def get_device_info(
    inspection_data: dict, ports_data: list[dict] | None = None
) -> ChassisInfo:
    """Get device info from Ironic inspection and port data.

    Args:
        inspection_data: Node inventory from Ironic inspection
        ports_data: Optional list of port dicts from Ironic API

    Returns:
        ChassisInfo object
    """
    try:
        chassis_info = chassis_info_from_ironic_data(inspection_data, ports_data)

        logger.info(
            "Successfully processed Ironic inspection data "
            "for %s (%s): %d interfaces, %d neighbors",
            chassis_info.bmc_hostname,
            chassis_info.serial_number,
            len(chassis_info.interfaces),
            len(chassis_info.neighbors),
        )

        return chassis_info

    except Exception:
        hostname = inspection_data.get("inventory", {}).get("hostname", "unknown")
        logger.exception("Failed to process Ironic inspection data for %s", hostname)
        raise
