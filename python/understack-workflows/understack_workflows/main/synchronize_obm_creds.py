import json
import sys

import ironicclient.common.apiclient.exceptions
from ironicclient.common.utils import args_array_to_patch

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.ironic.secrets import read_secret
from understack_workflows.node_configuration import IronicNodeConfiguration

logger = setup_logger(__name__)


def credential_secrets():
    """Reads Kubernetes Secret files with username/password credentials."""
    username = None
    password = None
    with open("/etc/obm/username") as f:
        # strip leading and trailing whitespace
        username = f.read().strip()

    with open("/etc/obm/password") as f:
        # strip leading and trailing whitespace
        password = f.read().strip()

    return [username, password]


def main():
    if len(sys.argv) < 1:
        raise ValueError(
            "Please provide node configuration in JSON format as first argument."
        )

    logger.info("Pushing device new node to Ironic.")
    client = IronicClient(
        svc_url=read_secret("IRONIC_SVC_URL"),
        username=read_secret("IRONIC_USERNAME"),
        password=read_secret("IRONIC_PASSWORD"),
        auth_url=read_secret("IRONIC_AUTH_URL"),
        tenant_name=read_secret("IRONIC_TENANT"),
    )

    interface_update_event = json.loads(sys.argv[1])
    logger.debug(f"Received: {interface_update_event}")

    node = IronicNodeConfiguration.from_event(interface_update_event)
    logger.debug(f"Checking if node with UUID {node.uuid} exists in Ironic.")

    try:
        ironic_node = client.get_node(node.uuid)
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug(f"Node: {node.uuid} not found in Ironic.")
        ironic_node = None
        sys.exit(1)

    STATES_ALLOWING_UPDATES = ["enroll", "manage"]
    if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
        logger.info(
            f"Device {node.uuid} is in a {ironic_node.provision_state} "
            f"provisioning state, so the updates are not allowed."
        )
        sys.exit(0)

    # Update OBM credentials
    expected_username, expected_password = credential_secrets()

    updates = [
        f"driver_info/redfish_username={expected_username}",
        f"driver_info/redfish_password={expected_password}",
    ]

    # using the behavior from the ironicclient code
    patches = args_array_to_patch("add", updates)

    response = client.update_node(node.uuid, patches)
    logger.info(f"Patching: {patches}")
    logger.info(f"Updated: {response}")
