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
    hostname: str | None = None
    ipv4_address: IPv4Interface | None = None
    ipv4_gateway: IPv4Address | None = None
    dhcp: bool = False
    remote_switch_mac_address: str | None = None
    remote_switch_port_name: str | None = None
    remote_switch_data_stale: bool = False


@dataclass(frozen=True)
class ChassisInfo:
    manufacturer: str
    model_number: str
    serial_number: str
    bmc_ip_address: str
    bios_version: str
    power_on: bool
    interfaces: list[InterfaceInfo]
    memory_gib: int
    cpu: str

    @property
    def bmc_interface(self) -> InterfaceInfo:
        return self.interfaces[0]

    @property
    def bmc_hostname(self) -> str:
        return str(self.bmc_interface.hostname)

    @property
    def neighbors(self) -> set:
        """A set of switch MAC addresses to which this chassis is connected."""
        return {
            interface.remote_switch_mac_address
            for interface in self.interfaces
            if interface.remote_switch_mac_address
        }


REDFISH_SYSTEM_ENDPOINT = "/redfish/v1/Systems/System.Embedded.1/"
REDFISH_ETHERNET_ENDPOINT = f"{REDFISH_SYSTEM_ENDPOINT}EthernetInterfaces/"
REDFISH_CONNECTION_ENDPOINT = (
    f"{REDFISH_SYSTEM_ENDPOINT}NetworkPorts/Oem/Dell/DellSwitchConnections/"
)
REDFISH_DRAC_NIC_ENDPOINT = (
    "/redfish/v1/Managers/iDRAC.Embedded.1/EthernetInterfaces/NIC.1"
)


def chassis_info(bmc: Bmc) -> ChassisInfo:
    """Query DRAC for basic system info via redfish.

    See Also:
        ProcessorSummary.Model and .CoreCount
        MemorySummary.TotalSystemMemoryGiB

    """
    chassis_data = bmc.redfish_request(REDFISH_SYSTEM_ENDPOINT)
    interfaces = interface_data(bmc)

    return ChassisInfo(
        manufacturer=chassis_data["Manufacturer"],
        model_number=chassis_data["Model"],
        serial_number=chassis_data["SKU"],
        bios_version=chassis_data["BiosVersion"],
        power_on=(chassis_data["PowerState"] == "On"),
        bmc_ip_address=bmc.ip_address,
        memory_gib=chassis_data.get("MemorySummary", {}).get("TotalSystemMemoryGiB", 0),
        interfaces=interfaces,
        cpu=chassis_data.get("ProcessorSummary", {}).get("Model", ""),
    )


def interface_data(bmc: Bmc) -> list[InterfaceInfo]:
    interfaces = [bmc_interface(bmc)] + in_band_interfaces(bmc)
    lldp = lldp_data_by_name(bmc)
    return [combine_lldp(lldp, interface) for interface in interfaces]


def combine_lldp(lldp, interface) -> InterfaceInfo:
    name = interface["name"]
    alternate_name = f"{name}-1"
    lldp_entry = lldp.get(name, lldp.get(alternate_name, {}))
    if not lldp_entry:
        logger.info(
            "LLDP info from BMC is missing for %s or %s, we only have LLDP info for %s",
            name,
            alternate_name,
            list(lldp.keys()),
        )
    return InterfaceInfo(**interface, **lldp_entry)


def bmc_interface(bmc) -> dict:
    """Retrieve DRAC BMC interface info via redfish API."""
    data = bmc.redfish_request(REDFISH_DRAC_NIC_ENDPOINT)
    ipv4_address, ipv4_gateway, dhcp = parse_ipv4(data["IPv4Addresses"])
    return {
        "name": "iDRAC",
        "description": "Dedicated iDRAC interface",
        "mac_address": data["MACAddress"].upper(),
        "hostname": data["HostName"],
        "ipv4_address": ipv4_address,
        "ipv4_gateway": ipv4_gateway,
        "dhcp": dhcp,
    }


def parse_ipv4(
    data: list[dict],
) -> tuple[None, None, None] | tuple[IPv4Interface, IPv4Address, bool]:
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
    """A Collection of Ethernet Interfaces for this System.

    If the redfish list of Ethernet Interfaces includes "foo" as well as "foo-1"
    then we disregard the latter.   The -1 suffix is used for "partitions" of a
    physical interface.  It seems to vary by device whether these are included
    in redfish output at all, and if they are, whether the mac address
    information is present in the base interface, the partition, or both.
    """
    index_data = bmc.redfish_request(REDFISH_ETHERNET_ENDPOINT)
    urls = [member["@odata.id"] for member in index_data["Members"]]

    return [
        interface_detail(bmc, url)
        for url in urls
        if re.sub(r"-\d$", "", url) not in urls
    ]


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
        "hostname": data["HostName"],
    }


def lldp_data_by_name(bmc) -> dict:
    """Retrieve LLDP information from DRAC using redfish API.

    Local interface names are standardised

    Remote Switch interface names have abbreviations expanded to cisco standard

    {
        "iDRAC": {
            "remote_switch_mac_address" : "C4:4D:04:48:61:80",
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
    ports = bmc.redfish_request(REDFISH_CONNECTION_ENDPOINT)["Members"]

    return {server_interface_name(port["Id"]): parse_lldp_port(port) for port in ports}


def parse_lldp_port(port_data: dict[str, str]) -> dict:
    """Adapt the Dell Redfish LLDP fields to our internal format.

    Remote Switch interface names have abbreviations expanded to cisco standard
    """
    mac = str(port_data["SwitchConnectionID"]).upper()
    port_name = normalize_interface_name(port_data["SwitchPortConnectionID"])
    stale = str(port_data["StaleData"]) != "NotStale"

    if mac in ["NOT AVAILABLE", "NO LINK", "NOT SUPPORTED"]:
        return {
            "remote_switch_mac_address": None,
            "remote_switch_port_name": None,
            "remote_switch_data_stale": stale,
        }
    else:
        return {
            "remote_switch_mac_address": normalise_mac(mac),
            "remote_switch_port_name": port_name,
            "remote_switch_data_stale": stale,
        }


def normalise_mac(mac: str) -> str:
    return ":".join(f"{int(n, 16):02X}" for n in mac.split(":"))


def server_interface_name(name: str) -> str:
    return "iDRAC" if name.startswith("iDRAC.Embedded") else name
