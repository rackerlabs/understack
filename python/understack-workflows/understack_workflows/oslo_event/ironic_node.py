from dataclasses import dataclass
from typing import Any
from uuid import UUID

from openstack.connection import Connection
from openstack.exceptions import ConflictException
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import save_output
from understack_workflows.helpers import setup_logger
from understack_workflows.oslo_event.keystone_project import is_project_svm_enabled

logger = setup_logger(__name__)


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
    if not is_project_svm_enabled(conn, event.lessee_undashed):
        return 0

    # Check if the server instance has an appropriate property.
    logger.info("Looking up Nova instance %s", event.instance_uuid)
    server = conn.get_server_by_id(event.instance_uuid)

    if not server:
        logger.error("Server %s not found", event.instance_uuid)
        save_output("storage", "not-found")
        return 1

    if server.metadata.get("storage") == "wanted":
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
