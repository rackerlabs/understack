from ipaddress import IPv4Interface
from uuid import UUID

import pynautobot

from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

DEVICE_INITIAL_STATUS = "Staged"
DEVICE_ROLE = "server"
INTERFACE_TYPE = "25gbase-x-sfp28"

def find_or_create(chassis_info: ChassisInfo, nautobot) -> UUID:
    """Update exsiting or create new device using the Nautobot API."""
    # TODO: performance: our single graphql query here fetches the device from
    # nautobot with all existing interfaces, macs, cable and connected switches.
    # We then query some of those items again, which adds unneccecary
    # round-trips to the DRAC.
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

    device = nautobot_server(nautobot, serial=chassis_info.serial_number)
    if not device:
        logger.info(
            f"Device {chassis_info.serial_number} not in Nautobot, creating"
        )

        switches = switches_for(nautobot, chassis_info)
        location_id, rack_id = location_from(switches.values())
        payload = server_device_payload(location_id, rack_id, chassis_info)
        logger.info(f"Server device: {payload}")
        nautobot.dcim.devices.create(**payload)
        # Re-run the graphql query to fetch any auto-created defaults from
        # nautobot (e.g. it automatically creates a BMC interface):
        device = nautobot_server(nautobot, serial=chassis_info.serial_number)
    else:
        switches = switches_for(nautobot, chassis_info)

    find_or_create_interfaces(nautobot, chassis_info, device['id'], switches)

    return device


def location_from(switches):
    locations = {(switch["location"]["id"], switch["rack"]["id"]) for switch in switches}
    if not locations:
        raise Exception(f"Can't find locations for {switches}")
    if len(locations) > 1:
        raise Exception(f"Connected switches in multiple racks or DCs: {locations}")
    return next(iter(locations))


def switches_for(nautobot, chassis_info: ChassisInfo) -> dict:
    switch_macs = {interface.remote_switch_mac_address
                    for interface in chassis_info.interfaces}
    return {mac: nautobot_switch(nautobot, mac) for mac in switch_macs}


def server_device_payload(location_id, rack_id, chassis_info):
    manufacturer = _parse_manufacturer(chassis_info.manufacturer)
    name = f"{manufacturer}-{chassis_info.serial_number}"

    return {
        "status": { "name": DEVICE_INITIAL_STATUS },
        "role": { "name": DEVICE_ROLE },
        "device_type": {
            "manufacturer" : { "name": manufacturer },
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


def nautobot_switch(nautobot, mac_address: str) -> dict:
    """Get switch by its MAC address.

    MAC addresses in SOT are normalized to upcase AA:BB:CC:DD:EE form.

    We store the MAC address in the "asset tag" field because there was nowhere
    else to put it.  Retrieving switches this way is really slow, could do with
    a better solution for storing switches' base mac addresses in Nautobot.

    TODO: can we pass an array of MAC addresses to this query and get all
    the switches in one go?
    """
    query = f"""{{
        devices(asset_tag: "{mac_address}"){{
            id name
            location {{ id name }}
            rack {{ id name }}
        }}
    }}"""

    result = nautobot.graphql.query(query)
    if not result.json or result.json.get("errors"):
        raise Exception(f"Nautobot switch graphql query failed: {result}")
    devices = result.json["data"]["devices"]

    if not devices:
        raise Exception(
            f"Looking for a switch in nautobot that matches the LLDP "
            f"info reported by server BMC - "
            f"No device found in nautobot with asset_tag {mac_address}"
        )
    if len(devices) > 1:
        raise Exception(
            f"Looking for a switch in nautobot that matches the LLDP "
            f"info reported by server BMC - "
            f"Multiple devices found with asset_tag {mac_address}"
        )

    return devices[0]


def nautobot_server(nautobot, serial: str) -> dict:
    query = f"""{{
        devices(serial: ["{serial}"]){{
            id name
            location {{ id name }}
            rack {{ id name }}
            interfaces {{
                id name
                type description mac_address
                status {{ name }}
                connected_interface {{
                    id name
                    device {{
                        id name
                        location {{id name }}
                        rack {{ id name }}
                        rel_vlan_group_to_devices {{
                            rel_vlan_group_to_devices {{ id name }}
                        }}
                    }}
                }}
                ip_addresses {{
                    id host
                    parent {{ prefix }}
                }}
            }}
        }}
    }}"""

    result = nautobot.graphql.query(query)
    if not result.json or result.json.get("errors"):
        raise Exception(f"Nautobot server graphql query failed: {result}")

    devices = result.json["data"]["devices"]

    if not devices:
        return None

    if len(devices) > 1:
        raise Exception(f"Multiple nautobot devices found with serial {serial}")

    return devices[0]


def find_or_create_interfaces(nautobot, chassis_info: ChassisInfo, device_id, switches):
    """Update Nautobot Device Interfaces using the Nautobot API."""
    for interface in chassis_info.interfaces:
        if interface.remote_switch_mac_address:
            setup_nautobot_interface(nautobot, interface, device_id, switches)

def setup_nautobot_interface(nautobot, interface: InterfaceInfo, device_id, switches):
    nautobot_int = find_or_create_interface(nautobot, interface, device_id, switches)

    if interface.ipv4_address:
        ip = assign_ip_address(
            nautobot,
            nautobot_int,
            interface.ipv4_address,
            interface.mac_address)
        ip = associate_ip_address(nautobot, nautobot_int, ip.id)

    connect_interface_to_switch(nautobot, interface, nautobot_int, switches)

def find_or_create_interface(nautobot, interface: InterfaceInfo, device_id: str, switches):
    id = {
        "device": device_id,
        "name": interface.name,
    }
    attrs = {
        "type": INTERFACE_TYPE,
        "status": "Active",
        "description": interface.description,
        "mac_address": interface.mac_address,
    }
    server_nautobot_interface = nautobot.dcim.interfaces.get(**id)
    if server_nautobot_interface:
        logger.info(
            f"Updating existing interface {interface.name} "
            f"{server_nautobot_interface.id} in Nautobot"
        )
        server_nautobot_interface.update(attrs)
    else:
        server_nautobot_interface = nautobot.dcim.interfaces.create(**id, **attrs)
        logger.info(
            f"Created interface {interface.name} "
            f"{server_nautobot_interface.id} in Nautobot"
        )
    return server_nautobot_interface

def connect_interface_to_switch(nautobot, interface, server_nautobot_interface, switches):
    connected_switch = switches[interface.remote_switch_mac_address]
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
            f"Interface {interface.name} connects to "
            f"{connected_switch['name']} {switch_port_name}"
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
        cable = nautobot.dcim.cables.create(**identity, **attrs)
        logger.info(f"Created cable {cable.id} in Nautobot")
    else:
        logger.info(f"Cable {cable.id} already exists in Nautobot")

def assign_ip_address(nautobot, nautobot_interface, ipv4_address: IPv4Interface, mac):
    try:
        ip = nautobot.ipam.ip_addresses.get(address=str(ipv4_address.ip))
        if ip and ip.type == "dhcp" and ip.custom_fields.get("pydhcp_mac") == mac:
            # Make our DHCP assignment permenant:
            ip.update(type="host", cf_pydhcp_expire=None)
        elif ip:
            logger.info(f"Nautobot IP already exists! {dict(ip)}")
        else:
            ip = nautobot.ipam.ip_addresses.create(
                address=str(ipv4_address.ip),
                status="Active",
                parent={
                    "type": "network",
                    "prefix": str(ipv4_address.network),
                },
            )
            logger.info(f"Created Nautobot IP {ip.id} for {ipv4_address}")
    except pynautobot.core.query.RequestError as e:
        raise Exception(
            f"Failed to assign {ipv4_address=} in Nautobot: {e}"
        ) from None
    return ip


def associate_ip_address(nautobot, nautobot_interface, ip_id):
    identity = {
        "ip_address": ip_id,
        "interface": nautobot_interface.id,
    }
    try:
        if nautobot.ipam.ip_address_to_interface.get(**identity):
            logger.info(f"IP address {ip_id} is already on {nautobot_interface.name}")
        else:
            nautobot.ipam.ip_address_to_interface.create(**identity, is_primary=True)
            logger.info(f"Associated IP address {ip_id} with {nautobot_interface.name}")
    except pynautobot.core.query.RequestError as e:
        raise Exception(
            f"Failed to associate IPAddress {ip_id} in Nautobot: {e}"
        ) from None
