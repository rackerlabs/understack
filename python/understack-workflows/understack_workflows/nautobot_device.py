import re
from uuid import UUID
from dataclasses import dataclass

from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.nautobot import Nautobot

logger = setup_logger(__name__)

DEVICE_INITIAL_STATUS = "Staged"
DEVICE_ROLE="server"

@dataclass
class Switch():
    name: str
    data_centre_id: str
    data_centre_name: str
    rack_id: str
    rack_name: str

def find_or_create(chassis_info: ChassisInfo, nautobot) -> UUID:
    """Update exsiting or create new device using the Nautobot API"""
    device = device_by_serial_number(nautobot, chassis_info.serial_number)
    if device is not None:
        raise Exception(f"Server already exists {chassis_info.serial_number=}")

    switches = switches_for(nautobot, chassis_info)
    data_centre_name, rack_name = location_from(switches.values())

    payload = server_device_payload(data_centre_name, rack_name, chassis_info)

    logger.info(f"Server device: {payload}")
    new_device = nautobot.dcim.devices.create(**payload)
    return dict(new_device)


def location_from(switches):
    locations = {(switch.data_centre_name, switch.rack_name) for switch in switches}
    if not locations:
        raise Exception(f"Can't find locations for {switches}")
    if len(locations) > 1:
        raise Exception(f"Connected switches in multiple racks or DCs: {locations}")
    return next(iter(locations))


def switches_for(nautobot, chassis_info: ChassisInfo) -> dict:
    switch_macs = {interface.remote_switch_mac_address
                    for interface in chassis_info.interfaces}
    return {mac: nautobot_switch(nautobot, mac) for mac in switch_macs}


def server_device_payload(data_centre_name, rack_name, chassis_info):
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
        "rack": { "name": rack_name },
        "location": {
            "name": data_centre_name,
            "location_type": { "name": "Site" },
        },
    }


def device_by_serial_number(nautobot, serial_number: str) -> dict:
    device = nautobot.dcim.devices.get(serial=serial_number)
    if device:
        logger.info("Updating existing Device with {serial_number} in Nautobot")
    else:
        logger.info("Device with {serial_number} not in Nautobot, creating")

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
            name location { id name }
            rack { id name }
        }
    }""" % mac_address

    result = nautobot.graphql.query(query)
    if not result.json or result.json.get("errors"):
        raise Exception(f"Nautobot switch graphql query failed: {result}")
    devices = result.json["data"]["devices"]

    if not devices:
        raise Exception(f"No device found in nautobot with asset_tag {mac_address}")
    if len(devices) > 1:
        raise Exception(f"Multiple devices found with asset_tag {mac_address}")

    return Switch(
        name=devices[0]["name"],
        data_centre_id=devices[0]["location"]["id"],
        data_centre_name=devices[0]["location"]["name"],
        rack_id=devices[0]["rack"]["id"],
        rack_name=devices[0]["rack"]["name"],
    )
