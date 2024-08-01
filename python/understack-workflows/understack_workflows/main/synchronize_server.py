import json
import sys

import ironicclient.common.apiclient.exceptions

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.ironic.secrets import read_secret
from understack_workflows.node_configuration import IronicNodeConfiguration

logger = setup_logger(__name__)


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
    logger.debug(f"Received: {json.dumps(interface_update_event, indent=2)}")
    update_data = interface_update_event["data"]

    node = IronicNodeConfiguration.from_event(interface_update_event)
    logger.debug(f"Checking if node UUID {node.uuid} exists in Ironic.")

    try:
        ironic_node = client.get_node(node.uuid)
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug(f"Node: {node.uuid} not found in Ironic, creating")
        ironic_node = node.create_node(client)

    logger.debug("Got Ironic node: %s", json.dumps(ironic_node.to_dict(), indent=2))

    STATES_ALLOWING_UPDATES = ["enroll"]
    if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
        logger.info(
            f"Device {node.uuid} is in a {ironic_node.provision_state} "
            f"provisioning state, so the updates are not allowed."
        )
        sys.exit(0)

    drac_ip = update_data["ip_addresses"][0]["host"]
    expected_address = f"https://{drac_ip}"
    current_address = ironic_node.driver_info.get("redfish_address", None)
    current_verify_ca = ironic_node.driver_info.get("redfish_verify_ca", None)

    patches = [
        replace_or_add_field(
            "/driver_info/redfish_address", current_address, expected_address
        ),
        replace_or_add_field(
            "/driver_info/redfish_verify_ca", current_verify_ca, False
        ),
    ]
    patches = [p for p in patches if p is not None]

    response = client.update_node(node.uuid, patches)
    logger.info(f"Patching: {patches}")
    logger.info(f"Updated: {response}")
