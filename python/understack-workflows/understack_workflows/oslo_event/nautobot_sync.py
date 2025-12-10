from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows import nautobot_device
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.ironic.inventory import get_device_info

logger = setup_logger(__name__)


def handle_provision_end(_: Connection, nautobot: Nautobot, event_data: dict) -> int:
    """Handle Ironic node provisioning END event.

    This handler is triggered after inspection completes to create/update
    the Nautobot device with inspection data. It fetches both node inventory
    and port data to get the most complete information.
    """
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

    node_uuid = str(payload_data["uuid"])
    ironic_client = IronicClient()

    # Get node inventory
    logger.info("Fetching inventory for node %s", node_uuid)
    node_inventory = ironic_client.get_node_inventory(node_ident=node_uuid)

    # Get ports for this node (has enriched data from inspection hooks)
    logger.info("Fetching ports for node %s", node_uuid)
    try:
        ports = ironic_client.list_ports(node_id=node_uuid)
        # Convert port objects to dicts
        ports_data = [
            {
                "uuid": p.uuid,
                "address": p.address,
                "name": getattr(p, "name", None),
                "extra": p.extra or {},
                "local_link_connection": p.local_link_connection or {},
                "pxe_enabled": p.pxe_enabled,
            }
            for p in ports
        ]
        logger.info("Found %d ports for node %s", len(ports_data), node_uuid)
    except Exception as e:
        logger.warning("Failed to fetch ports for node %s: %s", node_uuid, e)
        ports_data = None

    # Build device info with both inventory and port data
    device_info = get_device_info(node_inventory, ports_data)
    nb_device = nautobot_device.find_or_create(device_info, nautobot)

    logger.info("Updated Nautobot device: %s", nb_device)
    return 0
