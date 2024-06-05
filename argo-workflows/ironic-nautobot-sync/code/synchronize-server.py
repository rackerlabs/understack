from dataclasses import asdict
import json
import logging
import sys

import ironicclient.common.apiclient.exceptions


from ironic.client import IronicClient
from node_configuration import IronicNodeConfiguration
from redfish_driver_info import RedfishDriverInfo
from ironic.secrets import read_secret

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

if len(sys.argv) < 1:
    raise ValueError("Please provide node configuration in JSON format as first argument.")

logger.info("Pushing device new node to Ironic.")
client = IronicClient(
    svc_url=read_secret("IRONIC_SVC_URL"),
    username=read_secret("IRONIC_USERNAME"),
    password=read_secret("IRONIC_PASSWORD"),
    auth_url=read_secret("IRONIC_AUTH_URL"),
    tenant_name=read_secret("IRONIC_TENANT"),
)

def event_to_node_configuration(event: dict) -> IronicNodeConfiguration:
    node_config  = IronicNodeConfiguration()
    node_config.conductor_group = None
    node_config.driver = 'redfish'
    node_config.chassis_uuid = None
    node_config.uuid = event['device']['id']
    node_config.name = event['device']['name']

    return node_config


interface_update_event = json.loads(sys.argv[1])
logger.debug(f"Received: {interface_update_event}")
update_data = interface_update_event['data']

node_id = update_data['device']['id']
logger.debug(f"Checking if node with UUID: {node_id} exists in Ironic.")

try:
    ironic_node = client.get_node(node_id)
except ironicclient.common.apiclient.exceptions.NotFound:
    logger.debug(f"Node: {node_id} not found in Ironic.")
    ironic_node = None

if not ironic_node:
    node_config = event_to_node_configuration(update_data)
    response = client.create_node(node_config.create_arguments())
    logger.debug(response)
    ironic_node = client.get_node(node_id)

STATES_ALLOWING_UPDATES=['enroll']
if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
    logger.info(f"Device {node_id} is in a {ironic_node.provision_state} provisioning state, so the updates are not allowed.")
    sys.exit(0)

def replace_or_add_field(path, current_val, expected_val):
    if current_val == expected_val:
        return None
    if current_val is None:
        return {"op": "add", "path": path, "value": expected_val}
    else:
        return {"op": "replace", "path": path, "value": expected_val}

drac_ip = update_data['ip_addresses'][0]['host']
expected_address = f"https://{drac_ip}"
current_address = ironic_node.driver_info.get('redfish_address', None)
current_verify_ca = ironic_node.driver_info.get('redfish_verify_ca', None)

patches = [
    replace_or_add_field('/driver_info/redfish_address', current_address, expected_address),
    replace_or_add_field('/driver_info/redfish_verify_ca', current_verify_ca, False)
]
patches = [p for p in patches if p is not None]

response = client.update_node(node_id, patches)
logger.info(f"Patching: {patches}")
logger.info(f"Updated: {response}")
