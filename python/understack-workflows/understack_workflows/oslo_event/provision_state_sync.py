"""Handler for syncing Ironic provision state changes to Nautobot."""

from uuid import UUID

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.provision_state_mapper import ProvisionStateMapper
from understack_workflows.nautobot import Nautobot as NautobotHelper

logger = setup_logger(__name__)


def handle_provision_end(_: Connection, nautobot: Nautobot, event_data: dict) -> int:
    """Handle Ironic node provision state changes and sync to Nautobot.

    This handler updates the Nautobot device status and custom fields
    whenever a provision state change occurs. It runs for ALL provision
    state changes (not just specific states like deploying/inspecting).
    """
    payload = event_data.get("payload", {})
    payload_data = payload.get("ironic_object.data")

    if not payload_data:
        logger.error("Missing 'ironic_object.data' in event payload")
        return 1

    # Extract required fields
    node_uuid = payload_data.get("uuid")
    provision_state = payload_data.get("provision_state")

    if not node_uuid:
        logger.error("Missing 'uuid' in event payload")
        return 1

    if not provision_state:
        logger.error("Missing 'provision_state' in event payload")
        return 1

    logger.info("Syncing provision state for node %s: %s", node_uuid, provision_state)

    # Extract optional fields
    lessee = payload_data.get("lessee")
    resource_class = payload_data.get("resource_class")

    # Convert lessee to UUID if present
    tenant_id = None
    if lessee:
        try:
            tenant_id = UUID(lessee) if isinstance(lessee, str) else lessee
        except (ValueError, TypeError) as e:
            logger.warning("Invalid lessee UUID %s: %s", lessee, e)

    # Convert node UUID
    try:
        device_uuid = UUID(node_uuid) if isinstance(node_uuid, str) else node_uuid
    except (ValueError, TypeError) as e:
        logger.error("Invalid node UUID %s: %s", node_uuid, e)
        return 1

    # Translate Ironic provision state to Nautobot status
    new_status = ProvisionStateMapper.translate_to_nautobot(provision_state)

    if not new_status:
        logger.info(
            "Provision state %s has no Nautobot status mapping, skipping status update",
            provision_state,
        )
        # Still update custom fields even if status doesn't map
        new_status = None

    # Prepare custom fields to update
    custom_fields_to_update = {
        "ironic_provision_state": provision_state,
    }

    if resource_class:
        custom_fields_to_update["resource_class"] = resource_class

    # Initialize Nautobot helper
    nb_helper = NautobotHelper(
        url=nautobot.base_url,
        token=nautobot.token,
        logger=logger,
        session=nautobot,
    )

    try:
        # Update custom fields and tenant
        nb_helper.update_cf(
            device_id=device_uuid,
            tenant_id=tenant_id,
            fields=custom_fields_to_update,
        )
        logger.info(
            "Updated custom fields for device %s: %s",
            device_uuid,
            custom_fields_to_update,
        )

        # Update device status if we have a mapping
        if new_status:
            nb_helper.update_device_status(device_uuid, new_status)
            logger.info("Updated device %s status to %s", device_uuid, new_status)

        return 0

    except Exception:
        logger.exception("Failed to sync provision state for device %s", device_uuid)
        return 1
