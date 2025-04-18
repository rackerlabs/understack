import re
from dataclasses import dataclass
from ipaddress import IPv4Interface
from typing import Any

import pynautobot

from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

DEVICE_INITIAL_STATUS = "Planned"
DEVICE_ROLE = "server"
INTERFACE_TYPE = "25gbase-x-sfp28"
BMC_INTERFACE_TYPE = "1000base-t"


@dataclass
class NautobotInterface:
    """Represent a Nautobot Server Network Interface."""

    id: str
    name: str
    type: str
    description: str
    mac_address: str
    status: str
    ip_address: str | None
    neighbor_device_id: str | None
    neighbor_device_name: str | None
    neighbor_interface_id: str | None
    neighbor_interface_name: str | None
    neighbor_chassis_mac: str | None
    neighbor_location_name: str | None
    neighbor_rack_name: str | None
    vlan_group_name: str | None = None
    ucvni_group_name: str | None = None


@dataclass
class NautobotDevice:
    """Represent a Nautobot Server."""

    id: str
    name: str
    location_id: str
    location_name: str
    rack_id: str
    rack_name: str
    interfaces: list[NautobotInterface]


def find_or_create(chassis_info: ChassisInfo, nautobot) -> NautobotDevice:
    """Update existing or create new device using the Nautobot API."""
    # TODO: performance: our single graphql query here fetches the device from
    # nautobot with all existing interfaces, macs, cable and connected switches.
    # We then query some of those items again, which adds unnecessary
    # round-trips to Nautobot and/or DRAC.
    #
    # TODO: delete any extra items from nautobot (however we don't want to
    # delete cables that temporarily went down).
    #
    # TODO: look out for devices that have moved cabinet, or devices that are
    # taking over a switchport that is already occupied by some other device -
    # we should at least detect this and give a decent error message.
    #
    # TODO: make sure we are able to detect and remedy a change of switchport
    # (e.g. cable moved due to bad port on switch)
    #
    # TODO: could also verify compliant topology, e.g.:
    # - has a connection to both switch devices in vlan group
    # - has 4 NICs
    # - DRAC is connected to a DRAC switch
    # - in-band interfaces are connected to leaf switches
    # - we already verify that all connections are inside the same cabinet

    switches = switches_for(nautobot, chassis_info)
    device = nautobot_server(nautobot, serial=chassis_info.serial_number)
    if not device:
        logger.info("Device %s not in Nautobot, creating", chassis_info.serial_number)

        location_id, rack_id = location_from(list(switches.values()))
        payload = server_device_payload(location_id, rack_id, chassis_info)
        logger.debug("Server device: %s", payload)
        nautobot.dcim.devices.create(**payload)
        # Re-run the graphql query to fetch any auto-created defaults from
        # nautobot (e.g. it automatically creates a BMC interface):
        device = nautobot_server(nautobot, serial=chassis_info.serial_number)
        if not device:
            raise Exception("Failed to create device in Nautobot")

    find_or_create_interfaces(nautobot, chassis_info, device.id, switches)

    # Run the graphql query yet again, to include all the data we just populated
    # in nautobot. Fairly inefficient for the case where we didn't change
    # anything, but we need the accurate data.
    device = nautobot_server(nautobot, serial=chassis_info.serial_number)
    if not device:
        raise Exception("Failed to create device in Nautobot")
    return device


def location_from(switches):
    locations = {
        (switch["location"]["id"], switch["rack"]["id"]) for switch in switches
    }
    if not locations:
        raise Exception(f"Can't find locations for {switches}")
    if len(locations) > 1:
        raise Exception(f"Connected switches in multiple racks or DCs: {locations}")
    return next(iter(locations))


def switches_for(nautobot, chassis_info: ChassisInfo) -> dict[str, dict]:
    """Get all possible switches from the discovered LLDP neighbor information.

    We search for two possible mac addresses for each neighbor because some
    cisco switches report the chassis mac address while others report the
    interface mac address.
    """
    switch_macs = {
        interface.remote_switch_mac_address
        for interface in chassis_info.interfaces
        if interface.remote_switch_mac_address
    }
    base_switch_macs = {
        base_mac(
            interface.remote_switch_mac_address, str(interface.remote_switch_port_name)
        )
        for interface in chassis_info.interfaces
        if interface.remote_switch_mac_address
    }
    switches = nautobot_switches(nautobot, switch_macs.union(base_switch_macs))
    if not switches:
        raise Exception(
            f"There are no switch Devices in nautobot that match the LLDP info "
            f"reported by server BMC - I found no Devices where "
            f"chassis_mac_address is one of {switch_macs}"
        )
    return switches


def nautobot_switches(nautobot, mac_addresses: set[str]) -> dict[str, dict]:
    """Get switches by MAC address.

    Assumes switch MAC addresses are present in Nautobot in a custom field on
    Device called chassis_mac_address.

    Assumes that MAC addresses in Nautobot are normalized to upcase
    AA:BB:CC:DD:EE:FF form.

    returns a dict[mac_address] -> dict switch information indexed by mac
    """
    pattern = "|".join(mac_addresses)

    query = """
        query($pattern: [String!]){
            devices(cf_chassis_mac_address__re: $pattern){
                id name
                mac: cf_chassis_mac_address
                location { id name }
                rack { id name }
            }
        }
    """

    result = nautobot.graphql.query(query, variables={"pattern": pattern})
    if not result.json or result.json.get("errors"):
        raise Exception(f"Nautobot switch graphql query failed: {result}")
    switches = result.json["data"]["devices"]

    return {switch["mac"]: switch for switch in switches}


def nautobot_switch(all_switches: dict[str, Any], interface: InterfaceInfo):
    if interface.remote_switch_data_stale:
        logger.info("Warning: BMC marked LLDP data stale for %s", interface.name)

    if not interface.remote_switch_mac_address or not interface.remote_switch_port_name:
        raise ValueError(f"missing LDLDP info in {interface}")

    mac_address = interface.remote_switch_mac_address
    base_mac_address = base_mac(mac_address, interface.remote_switch_port_name)
    switch = all_switches.get(mac_address, all_switches.get(base_mac_address))
    if not switch:
        raise Exception(
            f"There is no switch Device in nautobot that matches the LLDP info "
            f"reported by server BMC for {interface} - I was looking for "
            f"chassis_mac_address= {mac_address}, or the calculated base mac "
            f"chassis_mac_address= {base_mac_address}."
        )
    return switch


def base_mac(mac: str, port_name: str) -> str:
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


def server_device_payload(
    location_id: str, rack_id: str, chassis_info: ChassisInfo
) -> dict:
    manufacturer = _parse_manufacturer(chassis_info.manufacturer)
    name = f"{manufacturer}-{chassis_info.serial_number}"

    return {
        "status": {"name": DEVICE_INITIAL_STATUS},
        "role": {"name": DEVICE_ROLE},
        "device_type": {
            "manufacturer": {"name": manufacturer},
            "model": chassis_info.model_number,
        },
        "name": name,
        "serial": chassis_info.serial_number,
        "rack": rack_id,
        "location": location_id,
    }


def _parse_manufacturer(name: str) -> str:
    if "DELL" in name.upper():
        return "Dell"
    raise ValueError(f"Server manufacturer {name} not supported")


def nautobot_server(nautobot, serial: str) -> NautobotDevice | None:
    query = """
        query($serial: String!){
            devices(serial: [$serial]){
                id name
                location { id name }
                rack { id name }
                interfaces {
                    id name
                    type description mac_address
                    status { name }
                    connected_interface {
                        id name
                        device {
                            id name
                            mac: cf_chassis_mac_address
                            location { id name }
                            rack { id name }
                            vlan_group: rel_vlan_group_to_devices {
                              name
                              ucvni_group: rel_ucvnigroup_vlangroup { name }
                            }
                        }
                    }
                    ip_addresses {
                        id host
                        parent { prefix }
                    }
                }
            }
        }
    """

    result = nautobot.graphql.query(query, variables={"serial": serial})
    if not result.json or result.json.get("errors"):
        raise Exception(f"Nautobot server graphql query failed: {result}")

    devices = result.json["data"]["devices"]

    if not devices:
        return None

    if len(devices) > 1:
        raise Exception(f"Multiple nautobot devices found with serial {serial}")

    return parse_device(devices[0])


def parse_device(data: dict) -> NautobotDevice:
    return NautobotDevice(
        id=data["id"],
        name=data["name"],
        location_id=data["location"]["id"],
        location_name=data["location"]["name"],
        rack_id=data["rack"]["id"],
        rack_name=data["rack"]["name"],
        interfaces=[parse_interface(i) for i in data["interfaces"]],
    )


def parse_interface(data: dict) -> NautobotInterface:
    ip_address = data["ip_addresses"][0] if data["ip_addresses"] else None
    connected = data["connected_interface"]
    connected_device = connected and connected.get("device")
    vlan_group = connected_device and connected_device.get("vlan_group")
    ucvni_group = vlan_group and vlan_group.get("ucvni_group")

    return NautobotInterface(
        id=data["id"],
        name=data["name"],
        mac_address=data["mac_address"],
        status=data["status"]["name"],
        type=data["type"],
        description=data["description"],
        ip_address=ip_address and ip_address["host"],
        neighbor_interface_id=connected and connected["id"],
        neighbor_interface_name=connected and connected["name"],
        neighbor_device_id=connected and connected["device"]["id"],
        neighbor_device_name=connected and connected["device"]["name"],
        neighbor_chassis_mac=connected and connected["device"]["mac"],
        neighbor_location_name=connected and connected["device"]["location"]["name"],
        neighbor_rack_name=connected and connected["device"]["rack"]["name"],
        vlan_group_name=vlan_group and vlan_group["name"],
        ucvni_group_name=ucvni_group and ucvni_group["name"],
    )


def find_or_create_interfaces(
    nautobot, chassis_info: ChassisInfo, device_id, switches: dict[str, dict]
):
    """Update Nautobot Device Interfaces using the Nautobot API."""
    for interface in chassis_info.interfaces:
        if interface.mac_address:
            setup_nautobot_interface(nautobot, interface, device_id, switches)


def setup_nautobot_interface(
    nautobot, interface: InterfaceInfo, device_id, switches: dict[str, dict]
):
    nautobot_int = find_or_create_interface(nautobot, interface, device_id)

    if interface.ipv4_address:
        ip = assign_ip_address(
            nautobot, nautobot_int, interface.ipv4_address, interface.mac_address
        )
        ip = associate_ip_address(nautobot, nautobot_int, ip.id)

    if interface.remote_switch_mac_address:
        connect_interface_to_switch(nautobot, interface, nautobot_int, switches)


def find_or_create_interface(nautobot, interface: InterfaceInfo, device_id: str):
    id = {
        "device": device_id,
        "name": interface.name,
    }
    attrs = {
        "type": interface_type(interface),
        "status": "Active",
        "description": interface.description,
        "mac_address": interface.mac_address,
    }
    server_nautobot_interface = nautobot.dcim.interfaces.get(**id)
    if server_nautobot_interface:
        logger.info(
            "Found existing interface %s %s in Nautobot",
            interface.name,
            server_nautobot_interface.id,
        )
        server_nautobot_interface.update(attrs)
    else:
        server_nautobot_interface = nautobot.dcim.interfaces.create(**id, **attrs)
        logger.info(
            "Created interface %s %s in Nautobot",
            interface.name,
            server_nautobot_interface.id,
        )
    return server_nautobot_interface


def interface_type(interface: InterfaceInfo) -> str:
    if interface.name in ["iDRAC", "iLO"]:
        return BMC_INTERFACE_TYPE
    else:
        return INTERFACE_TYPE


def connect_interface_to_switch(
    nautobot, interface, server_nautobot_interface, switches
):
    connected_switch = nautobot_switch(switches, interface)
    switch_port_name = interface.remote_switch_port_name

    switch_interface = nautobot.dcim.interfaces.get(
        device=connected_switch["id"],
        name=switch_port_name,
    )
    if switch_interface is None:
        raise Exception(
            f"{connected_switch['name']} has no interface called {switch_port_name}"
        )
    else:
        logger.info(
            "Interface %s connects to %s %s",
            interface.name,
            connected_switch["name"],
            switch_port_name,
        )

    identity = {
        "termination_a_id": switch_interface.id,
        "termination_b_id": server_nautobot_interface.id,
    }
    attrs = {
        "status": "Connected",
        "termination_a_type": "dcim.interface",
        "termination_b_type": "dcim.interface",
    }

    cable = nautobot.dcim.cables.get(**identity)
    if cable is None:
        try:
            cable = nautobot.dcim.cables.create(**identity, **attrs)
        except pynautobot.core.query.RequestError as e:  # type: ignore
            raise Exception(
                f"Failed to document discovered server in Nautobot - Server "
                f"Interface {server_nautobot_interface.id} {interface.name} "
                f"is detected as connected to Switch Interface "
                f"{switch_interface.id} {connected_switch['name']} "
                f"{switch_port_name}, but in Nautobot, when we try to create "
                f"that cable {identity}, Nautobot gave error {e}"
            ) from None
        logger.info("Created cable %s in Nautobot", cable.id)
    else:
        logger.info("Cable %s already correctly exists in Nautobot", cable.id)


def assign_ip_address(nautobot, nautobot_interface, ipv4_address: IPv4Interface, mac):
    """Find or create IP Address in Nautobot IPAM.

    If the existing IP address is a "dhcp" type then upgrade it to a "host" type.
    """
    try:
        ip = nautobot.ipam.ip_addresses.get(address=str(ipv4_address.ip))
        if ip and ip.type == "dhcp" and ip.custom_fields.get("pydhcp_mac") == mac:
            logger.info("Making DHCP lease permanent in Nautobot %s", dict(ip))
            ip.update(type="host", cf_pydhcp_expire=None)
        elif ip:
            logger.info("IP Address %s found, %s in Nautobot", ipv4_address, ip.id)
        else:
            ip = nautobot.ipam.ip_addresses.create(
                address=str(ipv4_address.ip),
                status="Active",
                parent={
                    "type": "network",
                    "prefix": str(ipv4_address.network),
                },
            )
            logger.info("Created Nautobot IP %s for %s", ip.id, ipv4_address)
    except pynautobot.core.query.RequestError as e:  # type: ignore
        raise Exception(f"Failed to assign {ipv4_address=} in Nautobot: {e}") from None
    return ip


def associate_ip_address(nautobot, nautobot_interface, ip_id):
    """Associate a given IP Address with a given Interface in Nautobot IPAM.

    If the IP Address is already associated with some other Interface then an
    Exception is raised.

    If the Interface is already associated to some other IP address then an
    Exception is raised.
    """
    existing_record = nautobot.ipam.ip_address_to_interface.get(ip_address=ip_id)

    if existing_record and existing_record.interface.id == nautobot_interface.id:
        logger.info(
            "IP Address %s {ip_id} already on %s", ip_id, nautobot_interface.name
        )
        return
    elif existing_record:
        raise Exception(
            f"Failed to document discovered server IP Address in Nautobot - "
            f"We need to associate IP address {ip_id} with the server "
            f"interface {nautobot_interface.id}, but the IP address is already "
            f"associated with another interface {existing_record.interface.id} "
            f"({existing_record.display})  Please resolve IP address clash and "
            f"then re-try enrollment."
        )

    existing_record = nautobot.ipam.ip_address_to_interface.get(
        interface=nautobot_interface.id
    )
    if existing_record:
        raise Exception(
            f"Failed to document discovered server IP Address in Nautobot - "
            f"We need to associate IP address {ip_id} with the server "
            f"interface {nautobot_interface.id}, but that interface is already "
            f"associated with a different IP address {existing_record.id} "
            f"({existing_record.display})  Please resolve IP address clash and "
            f"then re-try enrollment."
        )

    try:
        nautobot.ipam.ip_address_to_interface.create(
            ip_address=ip_id, interface=nautobot_interface.id, is_primary=True
        )
    except pynautobot.core.query.RequestError as e:  # type: ignore
        raise Exception(
            f"Failed to associate IPAddress {ip_id} in Nautobot: {e}"
        ) from None
    logger.info(
        "Associated IP address %s {ip_id} with %s", ip_id, nautobot_interface.name
    )
