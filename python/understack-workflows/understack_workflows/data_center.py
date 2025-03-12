import re
from dataclasses import dataclass

VLAN_GROUP_SUFFIXES = {
    "-1": "network",
    "-2": "network",
    "-1f": "storage",
    "-2f": "storage",
    "-3f": "storage-appliance",
    "-4f": "storage-appliance",
    "-1d": "bmc",
}

SWITCH_NAME_BY_MAC = {
    "C4:7E:E0:E3:EC:2B": "f20-1-1.iad3.rackspace.net",
    "C4:7E:E0:E4:2E:2F": "f20-1-2.iad3.rackspace.net",
    "C4:4D:84:48:7A:00": "f20-1-1d.iad3.rackspace.net",
    "C4:7E:E0:E4:10:7F": "f20-2-1.iad3.rackspace.net",
    "C4:7E:E0:E4:32:DF": "f20-2-2.iad3.rackspace.net",
    "C4:4D:84:48:61:80": "f20-2-1d.iad3.rackspace.net",
    "C4:7E:E0:E4:55:3F": "f20-3-1.iad3.rackspace.net",
    "C4:7E:E0:E4:03:37": "f20-3-2.iad3.rackspace.net",
    "C4:B3:6A:C8:33:80": "f20-3-1d.iad3.rackspace.net",
    "40:14:82:81:3E:E3": "f20-3-1f.iad3.rackspace.net",
    "C4:7E:E0:E7:A0:37": "f20-3-2f.iad3.rackspace.net",
}


@dataclass
class Switch:
    """A switch managed by understack."""

    name: str
    vlan_group_name: str | None


def switch_for_mac(mac: str, port_name: str) -> Switch:
    """Find switch by MAC Address.

    We "discover" our switch connections via LLDP, the iDRAC implementation of
    which provides us with the switch MAC address instead of its hostname,
    therefore we need to find the switch by MAC Address.

    The MAC address is one of the fields in the LLDP wire protocol, however some
    Cisco switches implement this incorrectly and provide the MAC address of the
    port, rather than the Chassis.  We work around this behaviour by searching
    for both MAC addresses.
    """
    mac = mac.upper()
    base_mac = _base_mac(mac, port_name)

    name = SWITCH_NAME_BY_MAC.get(mac) or SWITCH_NAME_BY_MAC.get(base_mac)
    if not name:
        raise ValueError(
            f"We don't have a switch that matches the LLDP info "
            f"reported by server BMC for {port_name}, neither "
            f"{mac}, or the calculated base mac {base_mac}."
        )

    return Switch(
        name=name,
        vlan_group_name=vlan_group_name(name),
    )


def vlan_group_name(switch_name: str) -> str | None:
    """Return a VLAN Group name based on our naming convention.

    >>> vlan_group_name("a1-1-1.abc1")
    "a1-1-network"
    """
    switch_name = switch_name.split(".")[0]

    for switch_name_suffix, vlan_group_suffix in VLAN_GROUP_SUFFIXES.items():
        if switch_name.endswith(switch_name_suffix):
            cabinet_name = switch_name.removesuffix(switch_name_suffix)
            return f"{cabinet_name}-{vlan_group_suffix}"
    return None


def _base_mac(mac: str, port_name: str) -> str:
    """Given a mac addr, return the mac addr which is <port_num> less.

    >>> base_mac("11:22:33:44:55:66", "Eth1/6")
    "11:22:33:44:55:60"
    """
    port_number = re.split(r"\D+", port_name)[-1]
    if not port_number:
        raise ValueError(f"Need numeric interface, not {port_name!r}")
    port_number = int(port_number)
    mac_number = int(re.sub(r"[^0-9a-fA-f]+", "", mac), 16)
    base = mac_number - port_number
    hexadecimal = f"{base:012X}"
    return ":".join(hexadecimal[i : i + 2] for i in range(0, 12, 2))
