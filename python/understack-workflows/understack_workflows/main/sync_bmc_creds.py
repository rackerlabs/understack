import json
import sys

import ironicclient.common.apiclient.exceptions
from ironicclient.common.utils import args_array_to_patch

from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.node_configuration import IronicNodeConfiguration

logger = setup_logger(__name__)


def get_args():
    if len(sys.argv) < 1:
        raise ValueError(
            "Please provide node configuration in JSON format as first argument."
        )

    return json.loads(sys.argv[1])


def main():
    interface_update_event = get_args()
    logger.debug(f"Received: {json.dumps(interface_update_event, indent=2)}")

    logger.info("Pushing device new node to Ironic.")
    client = IronicClient()

    node = IronicNodeConfiguration.from_event(interface_update_event)
    logger.debug(f"Checking if node with UUID {node.uuid} exists in Ironic.")

    try:
        ironic_node = client.get_node(node.uuid)
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug(f"Node: {node.uuid} not found in Ironic.")
        ironic_node = None
        sys.exit(1)

    STATES_ALLOWING_UPDATES = ["enroll", "manageable"]
    if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
        logger.info(
            f"Device {node.uuid} is in a {ironic_node.provision_state} "
            f"provision_state, so the updates are not allowed."
        )
        sys.exit(0)

    # Update BMC credentials
    expected_username = credential("bmc", "username")
    expected_password = credential("bmc", "password")

    updates = [
        f"driver_info/redfish_username={expected_username}",
        f"driver_info/redfish_password={expected_password}",
    ]

    # using the behavior from the ironicclient code
    patches = args_array_to_patch("add", updates)

    response = client.update_node(node.uuid, patches)
    logger.info(f"Patching: {patches}")
    logger.info(f"Updated: {response}")
