import re
from uuid import UUID
from dataclasses import dataclass

from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.nautobot import Nautobot

logger = setup_logger(__name__)

DEVICE_INITIAL_STATUS = "Staged"
DEVICE_ROLE="server"

def find_or_create(chassis_info: ChassisInfo, nautobot) -> UUID:
    """Update exsiting or create new device using the Nautobot API"""
    device = nautobot.dcim.devices.get(serial=chassis_info.serial_number)
    if device:
        # TODO: a graphql query here could fetch the device with all existing
        # interfaces, cable and connected switches:
        raise Exception(
            f"Updating existing Device not yet implemeted"
            f"Device {device.id} in Nautobot"
        )
    else:
        logger.info(
            f"Device {chassis_info.serial_number} not in Nautobot, creating"
        )

    switches = switches_for(nautobot, chassis_info)
    location_id, rack_id = location_from(switches.values())
    for mac, switch in switches.items():
        logger.info(f"Server {chassis_info.serial_number} -> {mac} -> {switch['name']}")

    payload = server_device_payload(location_id, rack_id, chassis_info)

    logger.info(f"Server device: {payload}")
    new_device = nautobot.dcim.devices.create(**payload)

    find_or_create_interfaces(nautobot, chassis_info, new_device.id, switches)

    return dict(new_device)


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


def device_by_serial_number(nautobot, serial_number: str) -> dict:
    device = nautobot.dcim.devices.get(serial=serial_number)
    if device:
        logger.info(f"Updating existing Device with {serial_number} in Nautobot")
    else:
        logger.info(f"Device with {serial_number} not in Nautobot, creating")

    return device


def _parse_manufacturer(name: str) -> str:
    name = name.upper()
    if "DELL" in name: return "Dell"
    if "HP" in name: return "HPE"
    raise ValueError(f"Server manufacturer {name} not supported")


def nautobot_switch(nautobot, mac_address: str) -> dict:
    """Get switch by its MAC address

    MAC addresses in SOT are normalized to upcase AA:BB:CC:DD:EE form.

    We store the MAC address in the "asset tag" field because there was nowhere
    else to put it.  Retrieving switches this way is really slow, could do with
    a better solution for storing mac addresses here.
    """
    query = """{
        devices(asset_tag: "%s"){
            id name
            location { id name }
            rack { id name }
        }
    }""" % mac_address

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


def find_or_create_interfaces(nautobot, chassis_info: ChassisInfo, device_id, switches):
    """Update Nautobot Device Interfaces using the Nautobot API"""

    for interface in chassis_info.interfaces:
        if interface.remote_switch_mac_address:
            find_or_create_interface(nautobot, interface, device_id, switches)

def find_or_create_interface(nautobot, interface: InterfaceInfo, device_id: str, switches):
    if interface.name == "iDRAC":
        server_nautobot_interface = nautobot.dcim.interfaces.get(
            device=device_id,
            name=interface.name,
        )
        logger.info(
            f"Using existing interface {interface.name} "
            f"{server_nautobot_interface.id} in Nautobot"
        )
    else:
        server_nautobot_interface = nautobot.dcim.interfaces.create(
            device=device_id,
            name=interface.name,
            type="25gbase-x-sfp28",
            status="Active",
            description=interface.description,
            mac_address=interface.mac_address,
        )
        logger.info(
            f"Created interface {interface.name} "
            f"{server_nautobot_interface.id} in Nautobot"
        )

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
            f"Interface {interface.name} connected to "
            f"{connected_switch['name']} {switch_port_name}"
        )

    nautobot.dcim.cables.create(
        status="Connected",
        termination_a_type="dcim.interface",
        termination_b_type="dcim.interface",
        termination_a_id=switch_interface.id,
        termination_b_id=server_nautobot_interface.id,
    )
