import json
import sys

import ironicclient.common.apiclient.exceptions

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


def replace_or_add_field(path, current_val, expected_val):
    if current_val == expected_val:
        return None
    if current_val is None:
        return {"op": "add", "path": path, "value": expected_val}
    else:
        return {"op": "replace", "path": path, "value": expected_val}


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

    STATES_ALLOWING_UPDATES = ["enroll"]
    if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
        logger.info(
            f"Device {node.uuid} is in a {ironic_node.provision_state} "
            f"provisioning state, so the updates are not allowed."
        )
        sys.exit(0)

    # Update OBM credentials
    expected_username, expected_password = credential_secrets()

    current_username = ironic_node.driver_info.get("redfish_username", None)
    current_password_is_set = ironic_node.driver_info.get("redfish_password", None)

    patches = [
        replace_or_add_field(
            "/driver_info/redfish_username", current_username, expected_username
        ),
        replace_or_add_field(
            "/driver_info/redfish_password", current_password_is_set, expected_password
        ),
    ]
    patches = [p for p in patches if p is not None]

    response = client.update_node(node.uuid, patches)
    logger.info(f"Patching: {patches}")
    logger.info(f"Updated: {response}")
