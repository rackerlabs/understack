from typing import Self
from uuid import UUID

from openstack.connection import Connection
from pydantic import BaseModel
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import save_output
from understack_workflows.helpers import setup_logger
from understack_workflows.oslo_event.keystone_project import is_project_svm_enabled

logger = setup_logger(__name__)


class IronicProvisionSetEvent(BaseModel):
    owner: UUID
    lessee: UUID
    instance_uuid: UUID
    node_uuid: UUID
    event: str

    @classmethod
    def from_event_dict(cls, data: dict) -> Self:
        payload = data.get("payload")
        if payload is None:
            raise ValueError("invalid event")

        payload_data = payload.get("ironic_object.data")
        if payload_data is None:
            raise ValueError("Invalid event. No 'ironic_object.data' in payload")

        return cls(
            owner=payload_data["owner"],
            lessee=payload_data["lessee"],
            instance_uuid=payload_data["instance_uuid"],
            event=payload_data["event"],
            node_uuid=payload_data["uuid"],
        )


def handle_provision_end(conn: Connection, _: Nautobot, event_data: dict) -> int:
    """Operates on an Ironic Node provisioning END event."""
    # Check if the project is configured with tags.
    event = IronicProvisionSetEvent.from_event_dict(event_data)
    logger.info("Checking if project %s is tagged with UNDERSTACK_SVM", event.lessee)
    if not is_project_svm_enabled(conn, event.lessee):
        return 0

    # Check if the server instance has an appropriate property.
    logger.info("Looking up Nova instance %s", event.instance_uuid)
    server = conn.get_server_by_id(event.instance_uuid)

    if not server:
        logger.error("Server %s not found", event.instance_uuid)
        save_output("storage", "not-found")
        return 1

    if server.metadata["storage"] == "wanted":
        save_output("storage", "wanted")
    else:
        logger.info("Server %s did not want storage enabled.", server.id)
        save_output("storage", "not-set")

    save_output("node_uuid", str(event.node_uuid))
    save_output("instance_uuid", str(event.instance_uuid))

    create_volume_connector(conn, event)
    return 0


def create_volume_connector(conn: Connection, event: IronicProvisionSetEvent):
    logger.info("Creating baremetal volume connector.")
    connector = conn.baremetal.create_volume_connector(  # pyright: ignore
        node_uuid=event.node_uuid,
        type="iqn",
        connector_id=instance_nqn(event.instance_uuid),
    )
    logger.debug("Created connector: %s", connector)
    return connector


def instance_nqn(instance_id: UUID):
    return f"nqn.2014-08.org.nvmexpress:uuid:{instance_id}"
