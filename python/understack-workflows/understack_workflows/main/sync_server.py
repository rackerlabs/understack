import json
import sys

import ironicclient.common.apiclient.exceptions
from ironicclient.common.utils import args_array_to_patch

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.node_configuration import IronicNodeConfiguration

logger = setup_logger(__name__)


def write_ironic_state_to_file(state):
    with open("/tmp/ironic_state.txt", "w") as f:
        f.write(state)


def get_args():
    if len(sys.argv) < 1:
        raise ValueError(
            "Please provide node configuration in JSON format as first argument."
        )

    return json.loads(sys.argv[1])


def get_ironic_node(node, ironic_client):
    logger.debug(f"Checking if node UUID {node.uuid} exists in Ironic.")

    try:
        ironic_node = ironic_client.get_node(node.uuid)
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug(f"Node: {node.uuid} not found in Ironic, creating")
        ironic_node = node.create_node(ironic_client)

    return ironic_node


def update_ironic_node(node, drac_ip, ironic_client):
    expected_address = f"https://{drac_ip}"

    updates = [
        f"name={node.name}",
        f"driver={node.driver}",
        f"driver_info/redfish_address={expected_address}",
        "driver_info/redfish_verify_ca=false",
    ]
    resets = [
        "bios_interface",
        "boot_interface",
        "inspect_interface",
        "management_interface",
        "power_interface",
        "vendor_interface",
        "raid_interface",
        "network_interface",
    ]

    # using the behavior from the ironicclient code
    patches = args_array_to_patch("add", updates)
    patches.extend(args_array_to_patch("remove", resets))
    logger.info(f"Patching: {patches}")

    return ironic_client.update_node(node.uuid, patches)


def main():
    interface_update_event = get_args()
    logger.debug(f"Received: {json.dumps(interface_update_event, indent=2)}")
    update_data = interface_update_event["data"]

    logger.info("Pushing device new node to Ironic.")
    ironic_client = IronicClient()

    node = IronicNodeConfiguration.from_event(interface_update_event)
    ironic_node = get_ironic_node(node, ironic_client)
    logger.debug(f"Got Ironic node: {json.dumps(ironic_node.to_dict(), indent=2)}")

    STATES_ALLOWING_UPDATES = ["enroll", "manageable"]
    if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
        logger.info(
            f"Device {node.uuid} is in a {ironic_node.provision_state} "
            f"provision_state, so the updates are not allowed."
        )
        sys.exit(0)

    drac_ip = update_data["ip_addresses"][0]["host"]

    response = update_ironic_node(node, drac_ip, ironic_client)
    logger.info(f"Updated: {response}")

    write_ironic_state_to_file(ironic_node.provision_state)
