import logging
from dataclasses import dataclass

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows.helpers import save_output
from understack_workflows.netapp.manager import NetAppManager

logger = logging.getLogger(__name__)

AGGREGATE_NAME = "aggr02_n02_NVME"
VOLUME_SIZE = "514GB"


@dataclass
class CinderVolumeTypeAccessEvent:
    project_id: str
    volume_type_id: str

    @classmethod
    def from_event_dict(cls, data: dict):
        payload = data.get("payload", {})

        project_id = payload.get("project_id")
        if project_id is None:
            raise Exception("no project_id in event payload")

        volume_type_id = payload.get("volume_type_id")
        if volume_type_id is None:
            raise Exception("no volume_type_id in event payload")

        return CinderVolumeTypeAccessEvent(
            project_id=project_id,
            volume_type_id=volume_type_id,
        )


def handle_volume_type_access_added(
    conn: Connection, _nautobot: Nautobot, event_data: dict
) -> int:
    if event_data.get("event_type") != "volume_type_project.access.add":
        logger.error("Received event that is not volume_type_project.access.add")
        return 1

    event = CinderVolumeTypeAccessEvent.from_event_dict(event_data)
    logger.info(
        "Starting FlexVol creation for volume type %s in project %s",
        event.volume_type_id,
        event.project_id,
    )

    vol_type = conn.block_storage.get_type(event.volume_type_id)  # pyright: ignore[reportAttributeAccessIssue]
    extra_specs = getattr(vol_type, "extra_specs", {}) or {}
    aggregate_name = extra_specs.get("aggregate_name", AGGREGATE_NAME)
    volume_size = extra_specs.get("volume_size", VOLUME_SIZE)

    netapp_manager = NetAppManager()

    if not netapp_manager.check_if_svm_exists(project_id=event.project_id):
        logger.warning(
            "SVM for project %s does not exist, skipping FlexVol creation",
            event.project_id,
        )
        save_output("volume_created", str(False))
        return 1

    netapp_manager.create_volume(
        project_id=event.project_id,
        volume_type_id=event.volume_type_id,
        volume_size=volume_size,
        aggregate_name=aggregate_name,
    )
    save_output("volume_created", str(True))
    save_output("volume_name", f"vol_{event.volume_type_id}")
    return 0


def handle_volume_type_access_removed(
    conn: Connection, _nautobot: Nautobot, event_data: dict
) -> int:
    if event_data.get("event_type") != "volume_type_project.access.remove":
        logger.error("Received event that is not volume_type_project.access.remove")
        return 1

    event = CinderVolumeTypeAccessEvent.from_event_dict(event_data)
    logger.info(
        "Starting FlexVol deletion for volume type %s in project %s",
        event.volume_type_id,
        event.project_id,
    )

    try:
        netapp_manager = NetAppManager()
        volume_name = f"vol_{event.volume_type_id}"
        deleted = netapp_manager.delete_volume(volume_name, force=False)
        save_output("volume_deleted", str(deleted))
    except Exception as e:
        logger.error(
            "Failed to delete FlexVol for volume type %s: %s",
            event.volume_type_id,
            e,
        )
        return 1

    return 0
