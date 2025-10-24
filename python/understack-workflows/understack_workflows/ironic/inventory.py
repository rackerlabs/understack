import re
from ipaddress import IPv4Interface

from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

MIN_REQUIRED_NEIGHBOR_COUNT = 3
LLDP_DISCOVERY_ATTEMPTS = 6


def linux_to_redfish(linux_interface_name: str) -> str:
    # Skip special interfaces
    if linux_interface_name in ["idrac", "lo", "docker0", "virbr0"]:
        return linux_interface_name

    # Pattern 1: Embedded interfaces (eno8303, eno8403)
    # Must check this FIRST before other eno patterns
    match = re.match(r"^eno8(\d)03$", linux_interface_name)
    if match:
        interface_num = int(match.group(1))
        nic_num = interface_num - 2
        return f"NIC.Embedded.{nic_num}-1-1"

    # Pattern 2: Integrated with PHY (eno3np0, eno4np1)
    match = re.match(r"^eno(\d+)n?p(\d+)$", linux_interface_name)
    if match:
        slot_num = int(match.group(1))
        port_num = slot_num - 2
        return f"NIC.Integrated.1-{port_num}"

    # Pattern 3: Simple integrated (eno1, eno2, eno3, eno4)
    match = re.match(r"^eno(\d+)$", linux_interface_name)
    if match:
        interface_num = int(match.group(1))
        return f"NIC.Integrated.1-{interface_num}-1"

    # Pattern 4: Slot interfaces (ens2f0np0, ens2f1np1)
    match = re.match(r"^ens\d+f(\d+)n?p\d+$", linux_interface_name)
    if match:
        func_num = int(match.group(1))
        port_num = func_num + 1
        return f"NIC.Slot.1-{port_num}"

    # No pattern matched
    return linux_interface_name


def discover_chassis_info_from_ironic(inspection_data: dict) -> ChassisInfo:
    """Process Ironic inspection data, validating LLDP neighbor discovery.

    Similar to the redfish discovery function, this ensures we have sufficient
    LLDP neighbor information before considering the discovery complete.

    Args:
        inspection_data: Raw inspection data from Ironic

    Returns:
        ChassisInfo: Processed chassis information

    Raises:
        Exception: If insufficient LLDP neighbors are discovered
    """
    device_info = chassis_info_from_ironic_data(inspection_data)

    # Check LLDP neighbor count
    neighbor_count = len(device_info.neighbors)

    if neighbor_count < MIN_REQUIRED_NEIGHBOR_COUNT:
        # Log interface details for debugging
        lldp_table = {
            interface.name: (
                f"{interface.remote_switch_mac_address}"
                f"/{interface.remote_switch_port_name}"
            )
            for interface in device_info.interfaces
            if interface.remote_switch_mac_address
        }

        logger.warning(
            "Insufficient LLDP neighbors discovered for %s, "
            "need %d or more, got %d: %s",
            device_info.bmc_hostname,
            MIN_REQUIRED_NEIGHBOR_COUNT,
            neighbor_count,
            lldp_table,
        )
        raise Exception(
            "Only %d LLDP neighbors discovered, but %d are required."
            % (neighbor_count, MIN_REQUIRED_NEIGHBOR_COUNT)
        )

    logger.info(
        "Successfully discovered chassis info for %s with %d LLDP neighbors",
        device_info.bmc_hostname,
        neighbor_count,
    )
    return device_info


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


def parse_interface_data(interface_data: dict, hostname: str) -> InterfaceInfo:
    lldp_info = parse_lldp_data(interface_data.get("lldp", []))

    # For server interfaces, ignore IP addresses (only iDRAC should have IP info)
    return InterfaceInfo(
        name=linux_to_redfish(interface_data["name"]),
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

    interfaces = [bmc_interface]
    for interface_data in inventory["interfaces"]:
        interfaces.append(parse_interface_data(interface_data, hostname))

    return ChassisInfo(
        manufacturer=system_vendor["manufacturer"],
        model_number=system_vendor["product_name"].split("(")[0].strip(),
        serial_number=system_vendor["serial_number"],
        bmc_ip_address=inventory["bmc_address"],
        bios_version=system_vendor["firmware"]["version"],
        power_on=True,  # Assume powered on since inspection is running
        interfaces=interfaces,
        memory_gib=int(memory_info["physical_mb"] / 1024),
        cpu=inventory["cpu"]["model_name"],
    )


class Inventory:
    """Data source that provides chassis information from Ironic inspection data."""

    def __init__(self, inspection_data: dict):
        """Initialize with Ironic inspection data.

        Args:
            inspection_data: Raw inspection data from Ironic
        """
        self.inspection_data = inspection_data
        self._chassis_info: ChassisInfo | None = None

    def get_chassis_info(self) -> ChassisInfo:
        if self._chassis_info is None:
            self._chassis_info = discover_chassis_info_from_ironic(self.inspection_data)
        return self._chassis_info

    @property
    def ip_address(self) -> str:
        return self.inspection_data["inventory"]["bmc_address"]

    @property
    def hostname(self) -> str:
        return self.inspection_data["inventory"]["hostname"]


def get_device_info(inspection_data: dict) -> ChassisInfo:
    try:
        data_source = Inventory(inspection_data)
        chassis_info = data_source.get_chassis_info()

        logger.info(
            "Successfully processed Ironic inspection data "
            "for %s (%s): %d interfaces, %d neighbors",
            chassis_info.bmc_hostname,
            chassis_info.serial_number,
            len(chassis_info.interfaces),
            len(chassis_info.neighbors),
        )

        return chassis_info

    except Exception as e:
        hostname = inspection_data.get("inventory", {}).get("hostname", "unknown")
        logger.error("Failed to enroll server from Ironic data for %s: %s", hostname, e)
        raise
