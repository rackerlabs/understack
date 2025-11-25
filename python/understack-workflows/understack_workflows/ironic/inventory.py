from ipaddress import IPv4Interface

from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


# Mapping of Linux interface names to Redfish-style names for Dell servers
# Based on Dell PowerEdge server interface naming conventions
DELL_INTERFACE_NAME_MAPPING = {
    # Embedded NICs
    "eno8303": "NIC.Embedded.1-1-1",
    "eno8403": "NIC.Embedded.2-1-1",
    # Integrated NICs
    "eno3np0": "NIC.Integrated.1-1",
    "eno4np1": "NIC.Integrated.1-2",
    # Slot NICs
    "ens2f0np0": "NIC.Slot.1-1",
    "ens2f1np1": "NIC.Slot.1-2",
}

# Special interfaces that should pass through unchanged for all manufacturers
SPECIAL_INTERFACES = {"idrac", "lo", "docker0", "virbr0"}


def linux_to_redfish(linux_interface_name: str, manufacturer: str) -> str:
    """Convert Linux interface name to Redfish format based on manufacturer.

    Args:
        linux_interface_name: The Linux kernel interface name (e.g., "eno3np0")
        manufacturer: The server manufacturer (e.g., "Dell Inc.", "HP", "HPE")

    Returns:
        For Dell servers: Redfish-style name (e.g., "NIC.Integrated.1-1")
        For HP/HPE servers: Original Linux interface name
        For unknown interfaces: Original Linux interface name
    """
    # Special interfaces always pass through unchanged
    if linux_interface_name in SPECIAL_INTERFACES:
        return linux_interface_name

    # Only apply Dell-specific mapping for Dell servers
    if "Dell" in manufacturer:
        return DELL_INTERFACE_NAME_MAPPING.get(
            linux_interface_name, linux_interface_name
        )

    # For HP/HPE and other manufacturers, return the Linux name as-is
    return linux_interface_name


def parse_lldp_data(lldp_raw: list[list]) -> dict[str, str | None]:
    """Parse LLDP TLV data from Ironic inspection format.

    LLDP TLVs are in format: [type, hex_encoded_value]
    Common types:
    - 1: Chassis ID
    - 2: Port ID
    - 4: Port Description
    - 5: System Name (not stored in Redfish format)
    """
    result: dict[str, str | None] = {
        "remote_switch_mac_address": None,
        "remote_switch_port_name": None,
    }

    if not lldp_raw:
        return result

    for tlv_type, hex_value in lldp_raw:
        if not hex_value:
            continue

        try:
            # Convert hex string to bytes
            data = bytes.fromhex(hex_value)

            if tlv_type == 1:  # Chassis ID
                # First byte is subtype, rest is the ID
                if len(data) > 1:
                    subtype = data[0]
                    if subtype == 4:  # MAC address subtype
                        if len(data) == 7:  # 1 byte subtype + 6 bytes MAC
                            mac_bytes = data[1:7]
                            mac = ":".join(f"{b:02X}" for b in mac_bytes)
                            result["remote_switch_mac_address"] = mac

            elif tlv_type == 2:  # Port ID
                # First byte is subtype, rest is port identifier
                if len(data) > 1:
                    port_name = data[1:].decode("utf-8", errors="ignore")
                    result["remote_switch_port_name"] = port_name

            elif tlv_type == 4:  # Port Description
                port_desc = data.decode("utf-8", errors="ignore")
                if not result["remote_switch_port_name"]:
                    result["remote_switch_port_name"] = port_desc

            elif tlv_type == 5:  # System Name
                # Redfish interfaces don't store system name, so we skip this
                pass

        except (ValueError, UnicodeDecodeError) as e:
            logger.debug("Failed to parse LLDP TLV type %s: %s", tlv_type, e)
            continue

    return result


def parse_interface_data(
    interface_data: dict, hostname: str, manufacturer: str
) -> InterfaceInfo:
    lldp_info = parse_lldp_data(interface_data.get("lldp", []))

    # For server interfaces, ignore IP addresses (only iDRAC should have IP info)
    return InterfaceInfo(
        name=linux_to_redfish(interface_data["name"], manufacturer),
        description=f"{interface_data.get('driver', 'Unknown')} interface",
        mac_address=interface_data["mac_address"].upper(),
        hostname=hostname,
        ipv4_address=None,  # Ignore IP addresses for server interfaces
        ipv4_gateway=None,
        dhcp=False,
        remote_switch_mac_address=lldp_info["remote_switch_mac_address"],
        remote_switch_port_name=lldp_info["remote_switch_port_name"],
        remote_switch_data_stale=False,  # Ironic data is typically fresh
    )


def chassis_info_from_ironic_data(inspection_data: dict) -> ChassisInfo:
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
        # TODO: For BMC, we assume management network is /26
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
    for interface_data in inventory["interfaces"]:
        interfaces.append(parse_interface_data(interface_data, hostname, manufacturer))

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


def get_device_info(inspection_data: dict) -> ChassisInfo:
    try:
        chassis_info = chassis_info_from_ironic_data(inspection_data)

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
