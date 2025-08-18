from dataclasses import dataclass

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import setup_logger
from understack_workflows.netapp_manager import NetAppManager

logger = setup_logger(__name__)


SVM_PROJECT_TAG = "UNDERSTACK_SVM"
AGGREGATE_NAME = "aggr02_n02_NVME"
VOLUME_SIZE = "1GB"


@dataclass
class KeystoneProjectEvent:
    project_id: str

    @classmethod
    def from_event_dict(cls, data: dict):
        payload = data.get("payload")
        if payload is None:
            raise Exception("Invalid event. No 'payload'")

        target = payload.get("target")
        if target is None:
            raise Exception("no target information in payload")

        project_id = target.get("id")
        if project_id is None:
            raise Exception("no project_id found in payload")

        return KeystoneProjectEvent(project_id)


def _keystone_project_tags(conn: Connection, project_id: str):
    project = conn.identity.get_project(project_id)  # pyright: ignore[reportAttributeAccessIssue]
    if hasattr(project, "tags"):
        return project.tags
    else:
        return []


def handle_project_created(
    conn: Connection, _nautobot: Nautobot, event_data: dict
) -> int:
    if event_data.get("event_type") != "identity.project.created":
        return 1

    event = KeystoneProjectEvent.from_event_dict(event_data)
    logger.info("Starting ONTAP SVM and Volume creation workflow.")
    tags = _keystone_project_tags(conn, event.project_id)
    logger.debug("Project %s has tags: %s", event.project_id, tags)
    if SVM_PROJECT_TAG not in tags:
        logger.info("The %s is missing, not creating SVM.", SVM_PROJECT_TAG)
        exit(0)

    netapp_manager = NetAppManager()
    netapp_manager.create_svm(
        project_id=event.project_id, aggregate_name=AGGREGATE_NAME
    )
    netapp_manager.create_volume(
        project_id=event.project_id,
        volume_size=VOLUME_SIZE,
        aggregate_name=AGGREGATE_NAME,
    )
    return 0
