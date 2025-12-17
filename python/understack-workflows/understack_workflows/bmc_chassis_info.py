# pylint: disable=E1131,C0103

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
    """Interface Information Data Class."""

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
    """Chassis Information Data Class."""

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
        """BMC Interface response."""
        return self.interfaces[0]

    @property
    def bmc_hostname(self) -> str:
        """BMC Hostname response."""
        return str(self.bmc_interface.hostname)

    @property
    def neighbors(self) -> set:
        """A set of switch MAC addresses to which this chassis is connected."""
        return {
            interface.remote_switch_mac_address
            for interface in self.interfaces
            if interface.remote_switch_mac_address
        }


def chassis_info(bmc: Bmc) -> ChassisInfo:
    """Query DRAC for basic system info via redfish.

    See Also:
        ProcessorSummary.Model and .CoreCount
        MemorySummary.TotalSystemMemoryGiB

    """
    chassis_data = bmc.redfish_request(bmc.system_path)
    interfaces = interface_data(bmc)

    return ChassisInfo(
        manufacturer=normalise_manufacturer(chassis_data["Manufacturer"]),
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
    """Interface parsed from BMC outputs."""
    bmc_interface_info = bmc_interface(bmc)
    interfaces = [bmc_interface_info] + in_band_interfaces(bmc)
    if get_system_vendor(bmc) == "Dell":
        lldp = lldp_data_by_name(bmc)
        return [combine_lldp(lldp, interface) for interface in interfaces]
    else:
        return [combine_lldp({}, interface) for interface in interfaces]


def combine_lldp(lldp, interface) -> InterfaceInfo:
    """Combined response, LLDP and Interface data."""
    name = interface["name"]
    alternate_name = f"{name}-1"
    lldp_entry = lldp.get(name, lldp.get(alternate_name, {}))
    if not lldp_entry:
        logger.info(
            "LLDP info from BMC is missing for %s or %s,"
            "we only have LLDP info for %s",
            name,
            alternate_name,
            list(lldp.keys()),
        )
    return InterfaceInfo(**interface, **lldp_entry)


def bmc_interface(bmc) -> dict:
    """Retrieve DRAC BMC interface info via redfish API."""
    _interface = bmc.redfish_request(bmc.manager_path + "/EthernetInterfaces/")[
        "Members"
    ][0]["@odata.id"]
    _data = bmc.redfish_request(_interface)
    ipv4_address, ipv4_gateway, dhcp = parse_ipv4(_data["IPv4Addresses"])
    data = {k.lower(): v for k, v in _data.items()}
    host_name = data.get("hostname")
    bmc_name = "iDRAC" if get_system_vendor(bmc) == "Dell" else "iLO"
    bmc_description = (
        "Dedicated iDRAC interface" if (bmc_name == "iDRAC") else data.get("name")
    )
    bmc_mac = data.get("macaddress")
    return {
        "name": bmc_name,
        "description": bmc_description,
        "mac_address": normalise_mac(bmc_mac)
        if (bmc_mac and bmc_mac != "")
        else bmc_mac,
        "hostname": host_name,
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
    return [interface for interface in interface_results]


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

    1) On a switch configured with `lldp chassis-id switch` this will be the
    mac you see in `show mac address-table static | in Lo0` or `sho vdc detail`
    commands.  Note that this lldp configuration option is only available
    starting in Nexus version 10.2(3)F

    2) On other nexus, this mac address will be the base mac address plus the
    port number, for example if the base mac address of the switch is
    11:11:11:11:11:00 then the LLDP mac address seen on port e1/2 would be
    11:11:11:11:11:02
    """
    _data = bmc.redfish_request(
        bmc.system_path + "/NetworkPorts/Oem/Dell/DellSwitchConnections/"
    )
    ports = _data["Members"]
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


def get_system_vendor(bmc: Bmc) -> str:
    """Read Vendor name from Oem reference."""
    _data = bmc.redfish_request(bmc.system_path)
    vendor = [key for key in _data["Oem"]][0]
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
