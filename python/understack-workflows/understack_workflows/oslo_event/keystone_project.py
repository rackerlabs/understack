from dataclasses import dataclass

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import setup_logger
from understack_workflows.netapp_manager import NetAppManager

logger = setup_logger(__name__)


SVM_PROJECT_TAG = "UNDERSTACK_SVM"
AGGREGATE_NAME = "aggr02_n02_NVME"
VOLUME_SIZE = "514GB"
OUTPUT_BASE_PATH = "/var/run/argo"


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
        logger.error("Received event that is not identity.project.created")
        return 1

    event = KeystoneProjectEvent.from_event_dict(event_data)
    logger.info("Starting ONTAP SVM and Volume creation workflow.")
    tags = _keystone_project_tags(conn, event.project_id)
    logger.debug("Project %s has tags: %s", event.project_id, tags)

    project_is_svm_enabled = SVM_PROJECT_TAG in tags
    _save_output("svm_enabled", str(project_is_svm_enabled))

    if not project_is_svm_enabled:
        logger.info("The %s is missing, not creating SVM.", SVM_PROJECT_TAG)
        return 0

    svm_name = None
    try:
        netapp_manager = NetAppManager()
        svm_name = _create_svm_and_volume(netapp_manager, event)
        _save_output("svm_created", str(True))
    finally:
        if not svm_name:
            svm_name = "not_returned"
        _save_output("svm_name", svm_name)
    return 0


def handle_project_updated(
    conn: Connection, _nautobot: Nautobot, event_data: dict
) -> int:
    if event_data.get("event_type") != "identity.project.updated":
        logger.error("Received event that is not identity.project.updated")
        return 1

    event = KeystoneProjectEvent.from_event_dict(event_data)
    logger.info("Starting ONTAP SVM and Volume create/update workflow.")
    tags = _keystone_project_tags(conn, event.project_id)
    logger.debug("Project %s has tags: %s", event.project_id, tags)

    project_is_svm_enabled = SVM_PROJECT_TAG in tags
    _save_output("svm_enabled", str(project_is_svm_enabled))

    svm_name = None
    try:
        netapp_manager = NetAppManager()
        svm_exists = netapp_manager.check_if_svm_exists(project_id=event.project_id)

        # Tag removed
        if not project_is_svm_enabled and svm_exists:
            logger.warning(
                "SVM os-%s exists on NetApp but project %s is no longer tagged with %s",
                event.project_id,
                event.project_id,
                SVM_PROJECT_TAG,
            )
            netapp_manager.cleanup_project(event.project_id)
        # Tag added
        elif project_is_svm_enabled:
            if svm_exists:
                _save_output("svm_created", str(False))
            else:
                svm_name = _create_svm_and_volume(netapp_manager, event)
            _save_output("svm_created", str(True))
    finally:
        if not svm_name:
            svm_name = "not_returned"
        _save_output("svm_name", svm_name)
    return 0


def handle_project_deleted(
    conn: Connection, _nautobot: Nautobot, event_data: dict
) -> int:
    if event_data.get("event_type") != "identity.project.deleted":
        logger.error("Received event that is not identity.project.deleted")
        return 1

    event = KeystoneProjectEvent.from_event_dict(event_data)
    logger.info("Starting ONTAP SVM and Volume delete workflow.")
    try:
        netapp_manager = NetAppManager()
        svm_exists = netapp_manager.check_if_svm_exists(project_id=event.project_id)

        if svm_exists:
            logger.info("SVM for project %s exists - cleaning it up.", event.project_id)
            netapp_manager.cleanup_project(event.project_id)
        else:
            logger.info("SVM for project %s did not exist.", event.project_id)
        _save_output("svm_created", str(False))
    except Exception as e:
        logger.error(e)
        return 1
    return 0


def _create_svm_and_volume(netapp_manager, event) -> str:
    svm_name = netapp_manager.create_svm(
        project_id=event.project_id, aggregate_name=AGGREGATE_NAME
    )
    netapp_manager.create_volume(
        project_id=event.project_id,
        volume_size=VOLUME_SIZE,
        aggregate_name=AGGREGATE_NAME,
    )
    return svm_name


def _save_output(name, value):
    with open(f"{OUTPUT_BASE_PATH}/output.{name}", "w") as f:
        return f.write(value)
