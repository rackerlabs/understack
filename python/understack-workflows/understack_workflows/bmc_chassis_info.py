# pylint: disable=E1131,C0103

import logging
import re
from dataclasses import dataclass
from ipaddress import IPv4Address
from ipaddress import IPv4Interface

from understack_workflows.bmc import Bmc

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InterfaceInfo:
    """Interface Information Data Class."""

    name: str
    description: str
    mac_address: str
    hostname: str | None = None
    ipv4_address: IPv4Interface | None = None
    ipv4_gateway: IPv4Address | None = None
    dhcp: bool = False


@dataclass(frozen=True)
class ChassisInfo:
    """Chassis Information Data Class."""

    manufacturer: str
    model_number: str
    serial_number: str
    bmc_ip_address: str
    bios_version: str
    power_on: bool
    bmc_interface: InterfaceInfo
    memory_gib: int
    cpu: str

    @property
    def bmc_hostname(self) -> str:
        """BMC Hostname response."""
        return str(self.bmc_interface.hostname)

    @property
    def dump(self) -> list[str]:
        return [
            f"{self.manufacturer} {self.model_number} serial {self.serial_number}",
            f"BIOS VERSION {self.bios_version}",
            f"BMC IP Address {self.bmc_ip_address}",
            f"Power on {self.power_on}",
        ]


def chassis_info(bmc: Bmc) -> ChassisInfo:
    """Query DRAC for basic system info via redfish.

    See Also:
        ProcessorSummary.Model and .CoreCount
        MemorySummary.TotalSystemMemoryGiB

    """
    chassis_data = bmc.redfish_request(bmc.system_path)

    return ChassisInfo(
        manufacturer=normalise_manufacturer(chassis_data["Manufacturer"]),
        model_number=chassis_data["Model"],
        serial_number=chassis_data["SKU"],
        bios_version=chassis_data["BiosVersion"],
        power_on=(chassis_data["PowerState"] == "On"),
        bmc_ip_address=bmc.ip_address,
        memory_gib=chassis_data.get("MemorySummary", {}).get("TotalSystemMemoryGiB", 0),
        bmc_interface=bmc_interface(bmc),
        cpu=chassis_data.get("ProcessorSummary", {}).get("Model", ""),
    )


def bmc_interface(bmc) -> InterfaceInfo:
    """Retrieve DRAC BMC interface info via redfish API."""
    _interface = bmc.redfish_request(bmc.manager_path + "/EthernetInterfaces/")[
        "Members"
    ][0]["@odata.id"]
    _data = bmc.redfish_request(_interface)
    ipv4_address, ipv4_gateway, dhcp = parse_ipv4(_data["IPv4Addresses"])
    data = {k.lower(): v for k, v in _data.items()}
    host_name = data.get("hostname")

    if get_system_vendor(bmc) == "Dell":
        bmc_name = "iDRAC"
        bmc_description = "Dedicated iDRAC interface"
    elif get_system_vendor(bmc) == "HP":
        bmc_name = "iLO"
        bmc_description = str(data.get("name"))
    else:
        bmc_name = "BMC"
        bmc_description = str(data.get("name"))

    bmc_mac = normalise_mac(str(data.get("macaddress")))

    return InterfaceInfo(
        name=bmc_name,
        description=bmc_description,
        mac_address=bmc_mac,
        hostname=host_name,
        ipv4_address=ipv4_address,
        ipv4_gateway=ipv4_gateway,
        dhcp=bool(dhcp),
    )


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

    If the redfish list of Ethernet Interfaces includes "foo" and also "foo-1"
    then we disregard the latter.  The -1 suffix is used for "partitions" of a
    physical interface.  It seems to vary by device whether these are included
    in redfish output at all, and if they are, whether the mac address
    information is present in the base interface, the partition, or both.
    Excludes removal of devices where no reference of -1 exists.
    """
    index_data = bmc.redfish_request(bmc.system_path + "/EthernetInterfaces/")
    urls = [member["@odata.id"] for member in index_data["Members"]]
    interface_results = [
        interface_detail(bmc, url)
        for url in urls
        if (not re.search(r"-\d$", url)) or (re.sub(r"-\d$", "", url) not in urls)
    ]
    return list(interface_results)


def interface_detail(bmc, path) -> dict:
    """Data about the given NIC.

    Interface names are standardised.

    Fetches MACAddress, Description

    Note, if we were to append "-1" to the URL, alternative info is available:

    InterfaceEnabled, LinkStatus, Status.Health, State.Enabled, SpeedMbps
    """
    data = bmc.redfish_request(path)
    _data = {k.lower(): v for k, v in data.items()}
    name = _data.get("name")
    hostname = _data.get("hostname", "")
    description = _data.get("description", "")
    mac_addr = _data.get("macaddress", "")
    return {
        "name": server_interface_name(data["Id"]),
        "description": description if description != "" else name,
        "mac_address": normalise_mac(mac_addr) if mac_addr != "" else mac_addr,
        "hostname": hostname,
    }


def get_system_vendor(bmc: Bmc) -> str:
    """Read Vendor name from Oem reference."""
    _data = bmc.redfish_request(bmc.system_path)
    vendor = next(iter(_data["Oem"]))
    return normalise_manufacturer(vendor)


def normalise_mac(mac: str) -> str:
    """Format mac address to match standard."""
    return ":".join(f"{int(n, 16):02X}" for n in mac.split(":"))


def server_interface_name(name: str) -> str:
    """Return 'iDRAC' in place of embedded name."""
    return "iDRAC" if name.startswith("iDRAC.Embedded") else name


def normalise_manufacturer(name: str) -> str:
    """Return a standard name for Manufacturer."""
    if "DELL" in name.upper():
        return "Dell"
    elif "HP" in name.upper():
        return "HP"
    raise ValueError(f"Server manufacturer {name} not supported")
