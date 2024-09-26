import ironicclient.common.apiclient.exceptions
from ironicclient.common.utils import args_array_to_patch

from understack_workflows.ironic.client import IronicClient
from understack_workflows.node_configuration import IronicNodeConfiguration

STATES_ALLOWING_UPDATES = ["enroll", "manageable"]

def create_or_update(node_uuid: str, bmc: Bmc, logger):
    client = IronicClient()

    logger.debug(f"Ensuring node with UUID {device_id} exists in Ironic")
    try:
        ironic_node = client.get_node(node_uuid)
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug(f"Node: {node_uuid} not found in Ironic, creating.")
        ironic_node = create_ironic_node(
            client, interface_name, node_uuid, device_hostname, bmc
        )
        return

    if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
        logger.info(
            f"Device {node_uuid} in Ironic is in a "
            f"{ironic_node.provision_state} provision_state, "
            f"so no updates are allowed."
        )
        return

    updates = [
        f"driver_info/redfish_username={bmc.username}",
        f"driver_info/redfish_password={bmc.password}",
    ]

    patches = args_array_to_patch("add", updates)
    logger.info(f"Updating Ironic node {node_uuid} {patches=}")

    response = client.update_node(node_uuid, patches)
    logger.info(f"Ironic node {uuid} Updated: {response=}")

    return ironic_node.provision_state


def create_ironic_node(
        client: IronicClient,
        interface_name: str,
        node_uuid: str,
        device_hostname: str,
        bmc: Bmc,
) -> IronicNodeConfiguration:
        driver = "idrac" if bmc.bmc_type == "iDRAC" else "redfish"

        return client.create_node(
            {
                device_id: node_uuid,
                device_name: device_hostname,
                driver: driver,
                driver_info: {
                    redfish_address: bmc.url(),
                    redfish_verify_ca: False,
                    redfish_username: bmc.username,
                    redfish_password: bmc.password,
                },
            }
        )
