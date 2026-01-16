import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from openstack.connection import Connection
from openstack.exceptions import ConflictException
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import save_output
from understack_workflows.oslo_event.keystone_project import is_project_svm_enabled

logger = logging.getLogger(__name__)


@dataclass
class IronicProvisionSetEvent:
    node_uuid: str
    event: str
    owner: str
    lessee: str
    instance_uuid: str

    @classmethod
    def from_event_dict(cls, data: dict[str, Any]) -> "IronicProvisionSetEvent":
        payload = data.get("payload")
        if payload is None:
            raise ValueError("Invalid event. No 'payload'")

        payload_data = payload.get("ironic_object.data")
        if payload_data is None:
            raise ValueError("Invalid event. No 'ironic_object.data' in payload")

        return cls(
            node_uuid=payload_data["uuid"],
            event=payload_data["event"],
            owner=payload_data["owner"],
            lessee=payload_data["lessee"],
            instance_uuid=payload_data["instance_uuid"],
        )

    @property
    def lessee_undashed(self) -> str:
        """Returns lessee without dashes."""
        return UUID(self.lessee).hex


def _extract_payload_data(event_data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract ironic_object.data from event payload."""
    payload = event_data.get("payload", {})
    if isinstance(payload, dict):
        return payload.get("ironic_object.data")
    return None


def handle_provision_end(
    conn: Connection, _: Nautobot, event_data: dict[str, Any]
) -> int:
    """Operates on an Ironic Node provisioning END event."""
    payload_data = _extract_payload_data(event_data)
    if not payload_data:
        logger.error("Could not extract payload data from event")
        return 1

    node_uuid = payload_data.get("uuid")

    # Skip if no lessee (not an instance deployment)
    if not payload_data.get("lessee"):
        logger.info("No lessee on node %s, skipping SVM check", node_uuid)
        return 0

    # Skip if no instance_uuid (not an instance deployment)
    if not payload_data.get("instance_uuid"):
        logger.info("No instance_uuid on node %s, skipping SVM check", node_uuid)
        return 0

    # Now safe to create the event object with all required fields
    event = IronicProvisionSetEvent.from_event_dict(event_data)

    logger.info("Checking if project %s is tagged with UNDERSTACK_SVM", event.lessee)
    svm_enabled = is_project_svm_enabled(conn, event.lessee_undashed)

    # Check if the server instance has an appropriate property.
    logger.info("Looking up Nova instance %s", event.instance_uuid)
    server = conn.get_server_by_id(event.instance_uuid)

    if not server:
        logger.error("Server %s not found", event.instance_uuid)
        save_output("storage", "not-found")
        return 1

    if server.metadata.get("storage") == "wanted" and not svm_enabled:
        logger.warning(
            "Server %s wanted storage but project does not have UNDERSTACK_SVM",
            server.id,
        )
        save_output("storage", "wanted-but-not-project")
    elif server.metadata.get("storage") == "wanted":
        save_output("storage", "wanted")
    else:
        logger.info("Server %s did not want storage enabled.", server.id)
        save_output("storage", "not-set")

    save_output("node_uuid", event.node_uuid)
    save_output("instance_uuid", event.instance_uuid)

    create_volume_connector(conn, event)
    return 0


def create_volume_connector(conn: Connection, event: IronicProvisionSetEvent):
    logger.info("Creating baremetal volume connector.")
    try:
        connector = conn.baremetal.create_volume_connector(  # pyright: ignore
            node_uuid=event.node_uuid,
            type="iqn",
            connector_id=instance_nqn(event.instance_uuid),
        )
        logger.debug("Created connector: %s", connector)
        return connector
    except ConflictException:
        logger.info("Connector already exists.")


def instance_nqn(instance_id: str | None) -> str:
    return f"nqn.2014-08.org.nvmexpress:uuid:{instance_id}"


def handle_instance_delete(_conn: Connection, _: Nautobot, event_data: dict) -> int:
    """DEPRECATED: This handler is no longer used.

    Instance delete events are now handled directly by the sensor using data filters.
    See: components/site-workflows/sensors/sensor-nova-oslo-event.yaml

    This function is kept for reference but should not be called.

    Original purpose: Operated on a Nova instance delete event to clean up storage networking.
    """
    logger.warning(
        "handle_instance_delete called but is deprecated. "
        "This event should be handled by the sensor directly."
    )
    payload = event_data.get("payload", {})
    instance_uuid = payload.get("instance_id")
    project_id = payload.get("tenant_id")

    if not instance_uuid or not project_id:
        logger.error("No instance_id found in delete event payload")
        return 1

    logger.info("Processing instance delete for {}, Tenant {}".format(instance_uuid, project_id))

    # Get the server to find the node_uuid
    try:

        # Check if this server had storage enabled
        if payload.metadata.get("storage") != "wanted":
            logger.info("Server %s did not have storage enabled, skipping cleanup", instance_uuid)
            save_output("server_storage_deleted", "False")
            return 0

        # Get node_uuid from the server's hypervisor_hostname or other field
        # The node_uuid might be in server properties
        node_uuid = payload.get("node")

        logger.info("Marking server storage for deletion: instance=%s, node=%s", instance_uuid, node_uuid)
        save_output("server_storage_deleted", "True")
        save_output("node_uuid", str(node_uuid) if node_uuid else "unknown")
        save_output("instance_uuid", str(instance_uuid))
        save_output("project_id", project_id)

        return 0

    except Exception as e:
        logger.exception("Error processing instance delete: %s", e)
        return 1
