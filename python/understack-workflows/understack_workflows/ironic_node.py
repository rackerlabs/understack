import ironicclient.common.apiclient.exceptions
from ironicclient.common.utils import args_array_to_patch

from understack_workflows.bmc import Bmc
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.node_configuration import IronicNodeConfiguration

STATES_ALLOWING_UPDATES = ["enroll", "manageable"]

logger = setup_logger(__name__)


def create_or_update(bmc: Bmc, name: str, manufacturer: str) -> IronicNodeConfiguration:
    """Note interfaces/ports are not synced here, that happens elsewhere."""
    client = IronicClient()
    driver = _driver_for(manufacturer)

    try:
        ironic_node = client.get_node(name)
        logger.debug(
            "Using existing baremetal node %s with name %s", ironic_node.uuid, name
        )
        update_ironic_node(client, bmc, ironic_node, name, driver)
        return ironic_node
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug("Baremetal Node with name %s not found in Ironic, creating.", name)
        return create_ironic_node(client, bmc, name, driver)


def update_ironic_node(client, bmc, ironic_node, name, driver):
    if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
        logger.info(
            "Baremetal node %s is in %s provision_state, so no updates are allowed",
            ironic_node.uuid,
            ironic_node.provision_state,
        )
        return

    updates = [
        f"name={name}",
        f"driver={driver}",
        f"driver_info/redfish_address={bmc.url()}",
        "driver_info/redfish_verify_ca=false",
        f"driver_info/redfish_username={bmc.username}",
        f"driver_info/redfish_password={bmc.password}",
        "boot_interface=http-ipxe",
        "inspect_interface=agent",
    ]

    patches = args_array_to_patch("add", updates)
    logger.info("Updating Ironic node %s patches=%s", ironic_node.uuid, patches)

    response = client.update_node(ironic_node.uuid, patches)
    logger.info("Ironic node %s Updated: response=%s", ironic_node.uuid, response)


def create_ironic_node(
    client: IronicClient,
    bmc: Bmc,
    name: str,
    driver: str,
) -> IronicNodeConfiguration:
    return client.create_node(
        {
            "name": name,
            "driver": driver,
            "driver_info": {
                "redfish_address": bmc.url(),
                "redfish_verify_ca": False,
                "redfish_username": bmc.username,
                "redfish_password": bmc.password,
            },
            "boot_interface": "http-ipxe",
            "inspect_interface": "agent",
        }
    )


def _driver_for(manufacturer: str) -> str:
    if manufacturer.startswith("Dell"):
        return "idrac"
    else:
        return "redfish"
