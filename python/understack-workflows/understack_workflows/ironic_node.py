import ironicclient.common.apiclient.exceptions
from flavor_matcher.flavor_spec import dataclass
from ironicclient.common.utils import args_array_to_patch

from understack_workflows.bmc import Bmc
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.node_configuration import IronicNodeConfiguration

STATES_ALLOWING_UPDATES = ["enroll", "manageable"]

logger = setup_logger(__name__)


@dataclass(frozen=True)
class NodeMetadata:
    uuid: str
    hostname: str
    manufacturer: str
    resource_class: str

    @property
    def driver(self):
        if self.manufacturer.startswith("Dell"):
            return "idrac"
        else:
            return "redfish"


def create_or_update(node_meta: NodeMetadata, bmc: Bmc):
    """Note interfaces/ports are not synced here, that happens elsewhere."""
    client = IronicClient()
    logger.debug(f"Ensuring node with UUID {node_meta.uuid} exists in Ironic")
    try:
        ironic_node = client.get_node(node_meta.uuid)
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug(f"Node: {node_meta.uuid} not found in Ironic, creating.")
        ironic_node = create_ironic_node(client, node_meta, bmc)
        return ironic_node.provision_state  # type: ignore

    if ironic_node.provision_state in STATES_ALLOWING_UPDATES:
        update_ironic_node(client, node_meta, bmc)
    else:
        logger.info(
            f"Device {node_meta.uuid} in Ironic is in a "
            f"{ironic_node.provision_state} provision_state, "
            f"so no updates are allowed."
        )

    return ironic_node.provision_state


def update_ironic_node(client, node_meta, bmc):
    updates = [
        f"name={node_meta.hostname}",
        f"driver={node_meta.driver}",
        f"driver_info/redfish_address={bmc.url()}",
        "driver_info/redfish_verify_ca=false",
        f"driver_info/redfish_username={bmc.username}",
        f"driver_info/redfish_password={bmc.password}",
        f"resource_class={node_meta.resource_class}",
    ]

    patches = args_array_to_patch("add", updates)
    logger.info(f"Updating Ironic node {node_meta.uuid} {patches=}")

    response = client.update_node(node_meta.uuid, patches)
    logger.info(f"Ironic node {node_meta.uuid} Updated: {response=}")


def create_ironic_node(
    client: IronicClient,
    node_meta: NodeMetadata,
    bmc: Bmc,
) -> IronicNodeConfiguration:
    return client.create_node(
        {
            "uuid": node_meta.uuid,
            "name": node_meta.hostname,
            "driver": node_meta.driver,
            "driver_info": {
                "redfish_address": bmc.url(),
                "redfish_verify_ca": False,
                "redfish_username": bmc.username,
                "redfish_password": bmc.password,
            },
            "resource_class": node_meta.resource_class,
        }
    )
