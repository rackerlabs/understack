from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows import nautobot_device
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.ironic.inventory import get_device_info

logger = setup_logger(__name__)


def handle_provision_end(_: Connection, nautobot: Nautobot, event_data: dict) -> int:
    """Handle Ironic node provisioning END event."""
    payload = event_data.get("payload", {})
    payload_data = payload.get("ironic_object.data")

    if not payload_data:
        raise ValueError("Missing 'ironic_object.data' in event payload")

    previous_provision_state = payload_data.get("previous_provision_state")
    if previous_provision_state != "inspecting":
        logger.info(
            "Skipping Nautobot update for previous_provision_state: %s",
            previous_provision_state,
        )
        return 0

    ironic_client = IronicClient()
    node_inventory = ironic_client.get_node_inventory(
        node_ident=str(payload_data["uuid"])
    )
    device_info = get_device_info(node_inventory)
    nb_device = nautobot_device.find_or_create(device_info, nautobot)

    logger.info("Updated Nautobot device: %s", nb_device)
    return 0
