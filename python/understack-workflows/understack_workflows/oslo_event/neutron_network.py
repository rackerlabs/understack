import logging
import os
from dataclasses import dataclass
from typing import Self
from typing import cast
from uuid import UUID

import pynautobot
from pynautobot.core.api import Api as Nautobot
from pynautobot.models.ipam import Record

from understack_workflows.nautobot import NautobotRequestError

logger = logging.getLogger(__name__)


@dataclass
class NetworkEvent:
    event_type: str
    network_uuid: UUID
    network_name: str
    tenant_id: UUID
    external: bool
    provider_segmentation_id: int

    @classmethod
    def from_event_dict(cls, data: dict) -> Self:
        network = data["payload"]["network"]
        return cls(
            data["event_type"],
            UUID(network["id"]),
            network["name"],
            UUID(network["project_id"]),
            bool(network["router:external"]),
            int(network["provider:segmentation_id"]),
        )


def handle_network_create_or_update(
    _conn, nautobot: Nautobot, event_data: dict, ucvni_group_name: str | None = None
) -> int:
    """Handle Openstack Neutron Network CRUD Event."""
    event = NetworkEvent.from_event_dict(event_data)

    logger.info("Handling Network create/update for %s", event.network_name)
    return sync_network_to_nautobot(
        nautobot,
        str(event.network_uuid),
        event.network_name,
        str(event.tenant_id),
        event.provider_segmentation_id,
        ucvni_group_name,
    )


def handle_network_delete(_conn, nautobot: Nautobot, event_data: dict) -> int:
    """Handle Openstack Neutron Network CRUD Event."""
    event = NetworkEvent.from_event_dict(event_data)

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
    if event.provider_segmentation_id is None:
        raise RuntimeError("Network %s missing provider:segmentation_id", id)

    payload = {
        "id": id,
        "name": event.network_name,
        "status": {"name": "Active"},
        "tenant": str(event.tenant_id),
        "ucvni_group": {"name": ucvni_group_name},
        "ucvni_id": event.provider_segmentation_id,
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
        namespace = cast(Record, namespace)
        if namespace:
            _delete_nautobot_prefixes_in_namespace(nautobot, str(namespace.id))
            response = namespace.delete()  # type: ignore
            logger.debug("Removed Nautobot namespace name=%s: %s", name, response)
        else:
            logger.debug("No namespace name=%s to clean up from Nautobot", name)
    except pynautobot.RequestError as e:
        raise NautobotRequestError(e) from e


def _delete_nautobot_prefixes_in_namespace(nautobot: Nautobot, namespace_id: str):
    dependent_prefixes = nautobot.ipam.prefixes.filter(namespace=namespace_id)
    for prefix in dependent_prefixes:
        prefix = cast(Record, prefix)
        prefix.delete()
        logger.info("Deleted dependent prefix %s from Nautobot", prefix.prefix)


def sync_network_to_nautobot(
    nautobot: Nautobot,
    network_id: str,
    network_name: str,
    tenant_id: str,
    segmentation_id: int | None = None,
    ucvni_group_name: str | None = None,
) -> int:
    """Sync a single network to Nautobot.

    Creates IPAM namespace and UCVNI for the network.

    Args:
        nautobot: Nautobot API client
        network_id: Network UUID
        network_name: Network name
        tenant_id: Tenant/project UUID
        segmentation_id: Provider segmentation ID (optional)
        ucvni_group_name: UCVNI group name (defaults to UCVNI_GROUP_NAME env var)

    Returns:
        0 on success, 1 on failure
    """
    try:
        # Create IPAM namespace
        _ensure_nautobot_ipam_namespace_exists(nautobot, network_id)

        # Create or update UCVNI if segmentation ID exists
        if segmentation_id:
            event = NetworkEvent(
                event_type="network.sync",
                network_uuid=UUID(network_id),
                network_name=network_name,
                tenant_id=UUID(tenant_id),
                external=False,
                provider_segmentation_id=segmentation_id,
            )
            if not _update_nautobot_ucvni(nautobot, event, ucvni_group_name):
                _create_nautobot_ucvni(nautobot, event, ucvni_group_name)

        return 0
    except Exception:
        logger.exception("Failed to sync network %s", network_id)
        return 1


def _update_nautobot_ucvni(
    nautobot: Nautobot,
    event: NetworkEvent,
    ucvni_group_name: str | None = None,
) -> bool:
    """Update existing UCVNI. Returns True if updated, False if not found."""
    ucvni_id = str(event.network_uuid)

    if ucvni_group_name is None:
        ucvni_group_name = os.getenv("UCVNI_GROUP_NAME")
    if ucvni_group_name is None:
        raise RuntimeError("Please set environment variable UCVNI_GROUP_NAME")

    payload = {
        "name": event.network_name,
        "status": {"name": "Active"},
        "tenant": str(event.tenant_id),
        "ucvni_group": {"name": ucvni_group_name},
        "ucvni_id": event.provider_segmentation_id,
    }

    try:
        response = nautobot.plugins.undercloud_vni.ucvnis.update(
            id=ucvni_id, data=payload
        )
        logger.info("Updated Nautobot UCVNI: %s", response)
        return True
    except pynautobot.RequestError as e:
        if e.req.status_code == 404:
            logger.debug("No pre-existing Nautobot UCVNI with id=%s", ucvni_id)
            return False
        raise NautobotRequestError(e) from e
