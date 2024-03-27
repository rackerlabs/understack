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
    # TODO: these should be changed to defaults in Ironic configuration
    node_config.conductor_group = None
    node_config.driver = 'redfish'
    node_config.network_interface = 'noop'
    node_config.management_interface = 'redfish'
    node_config.boot_interface = 'redfish-virtual-media'
    node_config.power_interface = 'redfish'
    node_config.rescue_interface = 'no-rescue'
    node_config.raid_interface = 'redfish'
    node_config.inspect_interface = 'redfish'
    node_config.bios_interface = 'redfish'
    node_config.vendor_interface = 'redfish'
    node_config.console_interface = 'no-console'
    node_config.deploy_interface = 'ramdisk'
    node_config.storage_interface = 'noop'

    node_config.chassis_uuid = None
    node_config.uuid = event['device']['id']
    node_config.name = event['device']['name']
    # Not available at that stage.
    # network_data_dict = asdict(network_data)
    # _validate_network_data(network_data_dict)

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

drac_ip = update_data['ip_addresses'][0]['host']
expected_driver_info = RedfishDriverInfo(
    redfish_address=f"https://{drac_ip}",
    redfish_system_id="/redfish/v1/Systems/1",
    redfish_username="root",
    redfish_password="REDACTED",
    redfish_auth_type="auto",
    redfish_verify_ca=False
)

if ironic_node.driver_info != asdict(expected_driver_info):
    logger.info(f"{node_id} Updating driver_info")
    patch = [{"op": "replace", "path": "/driver_info", "value": asdict(expected_driver_info)}]
    response = client.update_node(node_id, patch)
    logger.info(f"Updated: {response}")
