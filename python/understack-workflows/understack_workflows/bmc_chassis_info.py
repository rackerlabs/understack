import re
from dataclasses import dataclass
from ipaddress import IPv4Address
from ipaddress import IPv4Interface

from understack_workflows.bmc import Bmc
from understack_workflows.helpers import setup_logger
from understack_workflows.interface_normalization import normalize_interface_name

logger = setup_logger(__name__)


@dataclass(frozen=True)
class InterfaceInfo:
    name: str
    description: str
    mac_address: str
    ipv4_address: IPv4Interface | None = None
    ipv4_gateway: IPv4Address | None = None
    dhcp: bool = False
    remote_switch_mac_address: str | None = None
    remote_switch_port_name: str | None = None


@dataclass(frozen=True)
class ChassisInfo:
    manufacturer: str
    model_number: str
    serial_number: str
    bmc_ip_address: str
    bios_version: str
    interfaces: list[InterfaceInfo]

    @property
    def bmc_interface(self):
        return self.interfaces[0]


def chassis_info(bmc: Bmc) -> ChassisInfo:
    """Query DRAC for basic system info via redfish.

    See Also:
        ProcessorSummary.Model and .CoreCount
        MemorySummary.TotalSystemMemoryGiB

    """
    url = "/redfish/v1/Systems/System.Embedded.1/"
    chassis_data = bmc.redfish_request(url)

    return ChassisInfo(
        manufacturer=chassis_data["Manufacturer"],
        model_number=chassis_data["Model"],
        serial_number=chassis_data["SKU"],
        bios_version=chassis_data["BiosVersion"],
        bmc_ip_address=bmc.ip_address,
        interfaces=interface_data(bmc),
    )


def interface_data(bmc: Bmc) -> list[InterfaceInfo]:
    interfaces = [bmc_interface(bmc)] + in_band_interfaces(bmc)
    lldp = lldp_data_by_name(bmc)
    return [combine_lldp(lldp, interface) for interface in interfaces]


def combine_lldp(lldp, interface) -> InterfaceInfo:
    name = interface["name"]
    lldp_entry = lldp.get(name, {})
    if not lldp_entry:
        logger.info(
            f"LLDP info from BMC is missing for {name}, we only "
            f"have LLDP info for {list(lldp.keys())}"
        )
    return InterfaceInfo(**interface, **lldp_entry)


def bmc_interface(bmc) -> dict:
    """Retrieve DRAC BMC interface info via redfish API."""
    url = "/redfish/v1/Managers/iDRAC.Embedded.1/EthernetInterfaces/NIC.1"
    data = bmc.redfish_request(url)
    ipv4_address, ipv4_gateway, dhcp = parse_ipv4(data["IPv4Addresses"])
    return {
        "name": "iDRAC",
        "description": "Dedicated iDRAC interface",
        "mac_address": data["MACAddress"].upper(),
        "ipv4_address": ipv4_address,
        "ipv4_gateway": ipv4_gateway,
        "dhcp": dhcp,
    }


def parse_ipv4(data: list[dict]) -> tuple[IPv4Interface, IPv4Address, bool]:
    """Parse the iDRAC's representation of network interface configuration.

    Example input:

    "IPv4Addresses": [
        {
        "Address": "10.46.96.156",
        "AddressOrigin": "Static",
        "Gateway": "10.46.96.129",
        "SubnetMask": "255.255.255.192"
        }
    ]

    Only the first address in the input is considered.
    """
    if not data:
        return None, None, None

    dhcp = data[0]["AddressOrigin"] == "DHCP"
    address = data[0]["Address"]
    netmask = data[0]["SubnetMask"]
    gateway = data[0]["Gateway"]
    ipv4_address = IPv4Interface(f"{address}/{netmask}")
    ipv4_gateway = IPv4Address(gateway)
    return ipv4_address, ipv4_gateway, dhcp


def in_band_interfaces(bmc: Bmc) -> list[dict]:
    """A Collection of Ethernet Interfaces for this System."""
    url = "/redfish/v1/Systems/System.Embedded.1/EthernetInterfaces/"
    index_data = bmc.redfish_request(url)
    urls = [member["@odata.id"] for member in index_data["Members"]]

    return [interface_detail(bmc, url) for url in urls if interface_is_relevant(url)]


def interface_detail(bmc, path) -> dict:
    """Data about the given NIC.

    Interface names are standardised.

    Fetches MACAddress, Description

    Note, if we were to append "-1" to the URL, alternative info is available:

    InterfaceEnabled, LinkStatus, Status.Health, State.Enabled, SpeedMbps
    """
    data = bmc.redfish_request(path)
    return {
        "name": server_interface_name(data["Id"]),
        "description": data["Description"],
        "mac_address": data["MACAddress"].upper(),
    }


def lldp_data_by_name(bmc) -> dict:
    """Retrieve LLDP information from DRAC using redfish API.

    Local interface names are standardised

    Remote Switch interface names have abbreviations expanded to cisco standard

    {
        "iDRAC": {
            "remote_switch_mac_address" : "C4:4D:84:48:61:80",
            "remote_switch_port_name" : "GigabitEthernet1/0/3",
        },
        'NIC.Slot.1-1': {
            "remote_switch_mac_address": "C4:7E:E0:E4:32:DF",
            "remote_switch_port_name": "Ethernet1/6",
        },
    }

    The MAC address is from the remote switch - it matches the base MAC that is
    found in `show version` output on a 2960, on N9k it is one of two things:

    1) on a switch configured with `lldp chassis-id switch` this will be the the
    mac you see in `show mac address-table static | in Lo0` or `sho vdc detail`
    commands.  Note that this lldp configuration option is only available
    starting in Nexus version 10.2(3)F

    2) On other nexus, this mac address will be the base mac address plus the
    port number, for example if the base mac address of the switch is
    11:11:11:11:11:00 then the LLDP mac address seen on port e1/2 would be
    11:11:11:11:11:02
    """
    url = (
        "/redfish/v1/Systems/System.Embedded.1"
        "/NetworkPorts/Oem/Dell/DellSwitchConnections/"
    )
    ports = bmc.redfish_request(url)["Members"]

    return {server_interface_name(port["Id"]): parse_lldp_port(port) for port in ports}


def parse_lldp_port(port_data: dict[str, str]) -> dict:
    """Adapt the Dell Redfish LLDP fields to our internal format.

    Remote Switch interface names have abbreviations expanded to cisco standard
    """
    mac = str(port_data["SwitchConnectionID"]).upper()
    port_name = normalize_interface_name(port_data["SwitchPortConnectionID"])

    if mac in ["NOT AVAILABLE", "NO LINK"]:
        return {
            "remote_switch_mac_address": None,
            "remote_switch_port_name": None,
        }
    else:
        return {
            "remote_switch_mac_address": mac,
            "remote_switch_port_name": port_name,
        }


def interface_is_relevant(url: str) -> bool:
    return bool(re.match(r".*(iDRAC.Embedded.*|NIC.(Integrated|Slot).\d-\d)$", url))


def server_interface_name(name: str) -> str:
    if name.startswith("iDRAC.Embedded"):
        return "iDRAC"

    # remove the "-1" partition number from dell NIC ports
    slot_regexp = re.compile(r"(.*\.\d-\d)-\d")
    match = slot_regexp.match(name)
    if match:
        return match.group(1)

    return name
