import logging
import os
from dataclasses import dataclass
from typing import Self
from uuid import UUID

import pynautobot
from pynautobot.core.api import Api as Nautobot

from understack_workflows.nautobot import NautobotRequestError

logger = logging.getLogger(__name__)

APPLICABLE_NETWORK_TYPES = ["vxlan"]


@dataclass
class NetworkEvent:
    event_type: str
    network_uuid: UUID
    network_name: str
    tenant_id: UUID
    external: bool
    network_type: str | None
    physical_network: str | None
    segmentation_id: int | None

    @classmethod
    def from_event_dict(cls, data: dict) -> Self:
        network = data["payload"]["network"]
        return cls(
            data["event_type"],
            UUID(network["id"]),
            network["name"],
            UUID(network["project_id"]),
            bool(network["router:external"]),
            network["provider:network_type"],
            network["provider:physical_network"],
            network["provider:segmentation_id"],
        )


def handle_network_create_or_update(
    _conn, nautobot: Nautobot, event_data: dict, ucvni_group_name: str | None = None
) -> int:
    """Handle Openstack Neutron Network CRUD Event."""
    event = NetworkEvent.from_event_dict(event_data)

    if event.network_type not in APPLICABLE_NETWORK_TYPES:
        return 0

    _ensure_nautobot_ipam_namespace_exists(nautobot, str(event.network_uuid))
    _create_nautobot_ucvni(nautobot, event, ucvni_group_name)

    return 0


def handle_network_delete(_conn, nautobot: Nautobot, event_data: dict) -> int:
    """Handle Openstack Neutron Network CRUD Event."""
    event = NetworkEvent.from_event_dict(event_data)

    if event.network_type not in APPLICABLE_NETWORK_TYPES:
        return 0

    _delete_nautobot_ipam_namespace(nautobot, str(event.network_uuid))
    _delete_nautotbot_ucvni(nautobot, id=str(event.network_uuid))

    return 0


def _create_nautobot_ucvni(
    nautobot: Nautobot, event: NetworkEvent, ucvni_group_name: str | None = None
):
    id = str(event.network_uuid)

    if ucvni_group_name is None:
        ucvni_group_name = os.getenv("UCVNI_GROUP_NAME")
    if ucvni_group_name is None:
        raise RuntimeError("Please set environment variable UCVNI_GROUP_NAME")

    payload = {
        "id": id,
        "name": event.network_name,
        "status": {"name": "Active"},
        "tenant": str(event.tenant_id),
        "ucvni_group": {"name": ucvni_group_name},
        "ucvni_id": event.segmentation_id,
    }
    try:
        response = nautobot.plugins.undercloud_vni.ucvnis.create(payload)
        logger.info("Created Nautobot UCVNI: %s", response)
    except pynautobot.RequestError as error:
        if error.req.status_code == 400 and "this Id already exists" in error.error:
            logger.debug("UCVNI %s already existed in Nautobot", id)
        else:
            raise NautobotRequestError(error) from error


def _delete_nautotbot_ucvni(nautobot: Nautobot, id: str):
    """Remove a UCVNI with the specified ID, if it exists.

    Nautobot seems to respond HTTP 204 when deleting something that doesn't
    exist, so this is idempotent.
    """
    nautobot.plugins.undercloud_vni.ucvnis.delete([id])
    logger.debug("Deleted any Nautobot UCVNI with id %s", id)


def _ensure_nautobot_ipam_namespace_exists(nautobot: Nautobot, name: str):
    try:
        response = nautobot.ipam.namespaces.create(name=name)
        logger.debug("Created Nautobot namespace name=%s id=%s", name, response)
    except pynautobot.RequestError as error:
        if (
            error.req.status_code == 400
            and "namespace with this name already exists" in error.error
        ):
            logger.debug("namespace %s already existed in Nautobot", name)
        else:
            raise NautobotRequestError(error) from error


def _delete_nautobot_ipam_namespace(nautobot: Nautobot, name: str):
    """Delete namespace from Nautobot by NAME, if it exists."""
    try:
        namespace = nautobot.ipam.namespaces.get(name=name)
        if namespace:
            response = namespace.delete()  # type: ignore
            logger.debug("Removed Nautobot namespace name=%s: %s", name, response)
        else:
            logger.debug("No namespace name=%s to clean up from Nautobot", name)
    except pynautobot.RequestError as e:
        raise NautobotRequestError(e) from e
