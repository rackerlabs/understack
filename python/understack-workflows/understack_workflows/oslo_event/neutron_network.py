import logging
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from pynautobot.core.api import Api as Nautobot
from pynautobot.core.query import RequestError
from pynautobot.core.response import Record

logger = logging.getLogger(__name__)


def handle_network_create(
    _conn,
    nautobot: Nautobot,
    event_data: dict,
) -> int:
    """Handle Openstack Neutron Network CRUD Event."""
    event = NetworkEvent.from_event_dict(event_data)
    _ensure_nautobot_ipam_namespace_exists(nautobot, str(event.network_uuid))
    return 0


def handle_network_delete(_conn, nautobot: Nautobot, event_data: dict) -> int:
    """Handle Openstack Neutron Network CRUD Event."""
    event = NetworkEvent.from_event_dict(event_data)
    _clean_up_nautobot_ipam_namespace(nautobot, str(event.network_uuid))
    return 0


def _ensure_nautobot_ipam_namespace_exists(nautobot: Nautobot, name: str):
    try:
        response = nautobot.ipam.namespaces.create(name=name)
        logger.debug("Created Nautobot namespace name=%s id=%s", name, response)
    except RequestError as error:
        if (
            error.req.status_code == 400
            and "namespace with this name already exists" in error.error
        ):
            logger.debug("namespace %s already existed in Nautobot", name)
        else:
            raise error


def _clean_up_nautobot_ipam_namespace(nautobot: Nautobot, name: str):
    namespace = nautobot.ipam.namespaces.get(name=name)
    if namespace:
        response = namespace.delete()  # type: ignore
        logger.debug("Removed Nautobot namespace name=%s: %s", name, response)


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
