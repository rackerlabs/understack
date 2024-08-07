import logging
import os
from ironic.client import IronicClient
import pynautobot
import argparse
from uuid import UUID
from typing import List, Dict
from enum import Enum
import sys

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


ALLOWED_STATES = ["enroll", "inspecting", "inspect wait", "manageable", "available"]
DRIVER_MAP = {
    "redfish": {
        "bios-interface": "redfish",
        "inspect-interface": "redfish",
        "management-interface": "redfish",
        "power-interface": "redfish",
        "vendor-interface": "redfish",
        "raid-interface": "redfish",
    },
    "idrac": {
        "bios-interface": "idrac-redfish",
        "inspect-interface": "idrac-redfish",
        "management-interface": "idrac-redfish",
        "power-interface": "idrac-redfish",
        "vendor-interface": "idrac-redfish",
        "raid-interface": "idrac-redfish",
    },
    "ilo": {
        "bios-interface": "ilo",
        "inspect-interface": "ilo",
        "management-interface": "ilo",
        "power-interface": "ilo",
        "vendor-interface": "ilo",
        "raid-interface": "ilo",
    },
    # ilo5 hardware type supports all the ilo interfaces, except for boot and raid interfaces
    "ilo5": {
        "bios-interface": "ilo",
        "inspect-interface": "ilo",
        "management-interface": "ilo",
        "power-interface": "ilo",
        "vendor-interface": "ilo",
        "raid-interface": "ilo5",
    },
}


class OBMType(str, Enum):
    iDRAC = "idrac"
    iLO = "ilo"


class IronicDriver(str, Enum):
    iDRAC = "idrac"
    iLO = "ilo"
    iLO5 = "ilo5"
    REDFISH = "redfish"


def get_obm_type_version(device_id: UUID) -> tuple[OBMType, int]:
    """Return the type and version of the OBM controller"""

    nautobot_api = os.environ["NAUTOBOT_API"]
    nautobot_token = os.environ["NAUTOBOT_TOKEN"]
    nautobot = pynautobot.api(nautobot_api, nautobot_token)
    platform = nautobot.dcim.platforms.get(devices=device_id)
    if not platform:
        raise Exception(f"Unable to locate a Platform for Device {device_id}.")

    # example platform names 'Dell iDRAC9', ' HPE iLO5'
    platform_name = platform.name.lower()
    obm_type = None
    obm_version = None
    if "idrac" in platform_name:
        obm_type = OBMType.iDRAC
        obm_version = int(platform_name.split("idrac")[1])
    if "ilo" in platform_name:
        obm_type = OBMType.iLO
        obm_version = int(platform_name.split("ilo")[1])

    if obm_type is None or obm_version is None:
        raise Exception("Unable to determine obm_type or obm_version from Nautobot Platform.")

    return obm_type, obm_version


def get_ironic_driver_type(device_id: UUID) -> str:
    """Return the Nautobot OBM hardware type"""

    obm_type, obm_version = get_obm_type_version(device_id)

    ironic_driver = None
    if obm_type == "idrac":
        ironic_driver = IronicDriver.iDRAC
    elif obm_type == "ilo":
        if obm_version == 4:
            ironic_driver = IronicDriver.iLO
        if obm_version == 5:
            ironic_driver = IronicDriver.iLO5
        if obm_version == 6:
            ironic_driver = IronicDriver.REDFISH
    else:
        raise Exception(f"Unexpected obm_type: {obm_type}")

    if not ironic_driver:
        raise Exception("Unable to determine the Ironic driver")

    return ironic_driver.value


def check_node_status(device_id: UUID) -> bool:
    node = client.get_node(device_id)
    return node.provision_state in ALLOWED_STATES


def get_node_patch(ironic_driver) -> List[Dict]:
    interfaces = DRIVER_MAP[ironic_driver]
    patch = [
        {"op": "replace", "path": "/driver", "value": ironic_driver},
        {"op": "replace", "path": "/bios_interface", "value": interfaces["bios-interface"]},
        {"op": "replace", "path": "/inspect_interface", "value": interfaces["inspect-interface"]},
        {"op": "replace", "path": "/management_interface", "value": interfaces["management-interface"]},
        {"op": "replace", "path": "/power_interface", "value": interfaces["power-interface"]},
        {"op": "replace", "path": "/vendor_interface", "value": interfaces["vendor-interface"]},
        {"op": "replace", "path": "/raid_interface", "value": interfaces["raid-interface"]},
    ]
    return patch


def main(args):
    device_id = args.device_id
    logger.setLevel(args.loglevel)

    if not check_node_status(device_id):
        logger.error(f"Ironic Node not in State {ALLOWED_STATES}")
        sys.exit(1)

    logger.info("Fetching Hardware type from Nautobot")
    ironic_driver = get_ironic_driver_type(device_id)
    logger.info(f"Ironic hardware type identified as: {ironic_driver}")

    patch = get_node_patch(ironic_driver)
    client.update_node(device_id, patch)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update Ironic ports from Nautobot Interfaces")
    parser.add_argument("--device-id", required=True, help="Ironic Node and Nautobot Device ID", type=UUID)
    parser.add_argument("--debug", action="store_const", dest="loglevel", const=logging.DEBUG, default=logging.WARNING)
    args = parser.parse_args()

    client = IronicClient(
        svc_url=os.environ["IRONIC_SVC_URL"],
        username=os.environ["IRONIC_USERNAME"],
        password=os.environ["IRONIC_PASSWORD"],
        auth_url=os.environ["IRONIC_AUTH_URL"],
        tenant_name=os.environ["IRONIC_TENANT"],
    )

    main(args)
