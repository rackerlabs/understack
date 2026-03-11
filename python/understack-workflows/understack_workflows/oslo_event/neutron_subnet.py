import logging
from dataclasses import dataclass
from typing import Self
from uuid import UUID

import pynautobot
from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

from understack_workflows.nautobot import NautobotRequestError

logger = logging.getLogger(__name__)


@dataclass
class SubnetEvent:
    event_type: str
    subnet_uuid: UUID
    subnet_name: str
    tenant_uuid: UUID
    network_uuid: UUID
    cidr: str
    gateway_ip: str | None
    external: bool
    ip_version: int | None
    subnetpool_id: UUID | None

    @classmethod
    def from_event_dict(cls, data: dict) -> Self:
        subnet = data["payload"]["subnet"]
        return cls(
            data["event_type"],
            UUID(subnet["id"]),
            subnet["name"],
            UUID(subnet["project_id"]),
            UUID(subnet["network_id"]),
            subnet["cidr"],
            subnet["gateway_ip"],
            bool(subnet["router:external"]),
            subnet["ip_version"],
            subnet["subnetpool_id"] and UUID(subnet["subnetpool_id"]),
        )


def handle_subnet_create_or_update(
    _conn: Connection, nautobot: Nautobot, event_data: dict
) -> int:
    """Handle Openstack Neutron Subnet create/update Event."""
    subnet = SubnetEvent.from_event_dict(event_data)

    logger.info("Handling Subnet create/update for %s", subnet.subnet_name)
    return sync_subnet_to_nautobot(
        nautobot,
        str(subnet.subnet_uuid),
        str(subnet.network_uuid),
        str(subnet.tenant_uuid),
        subnet.cidr,
        subnet.external,
    )


def handle_subnet_delete(
    _conn: Connection, nautobot: Nautobot, event_data: dict
) -> int:
    """Handle Openstack Neutron Subnet Delete Event, delete by ID."""
    event = SubnetEvent.from_event_dict(event_data)
    id = str(event.subnet_uuid)

    try:
        nautobot.ipam.prefixes.delete([id])
        logger.info("Deleted Nautobot prefix id=%s", id)
        return 0
    except pynautobot.RequestError as e:
        raise NautobotRequestError(e) from e


def _update_nautobot_prefix(nautobot: Nautobot, id: str, payload: dict) -> bool:
    """Attempt to update an existing record via PATCH."""
    try:
        response = nautobot.ipam.prefixes.update(id=id, data=payload)
        logger.info("Updated existing Nautobot prefix id=%s: %s", id, response)
        return True
    except pynautobot.RequestError as e:
        if e.req.status_code == 404:
            logger.debug("No pre-existing Nautobot prefix with id=%s", id)
            return False
        raise NautobotRequestError(e) from e


def _create_nautobot_prefix(nautobot, payload: dict):
    try:
        response = nautobot.ipam.prefixes.create(payload)
        logger.info("Created Nautobot prefix: %s", response)
    except pynautobot.RequestError as e:
        raise NautobotRequestError(e) from e


def sync_subnet_to_nautobot(
    nautobot: Nautobot,
    subnet_id: str,
    network_id: str,
    tenant_id: str,
    cidr: str,
    is_external: bool = False,
) -> int:
    """Sync a single subnet to Nautobot.

    Args:
        nautobot: Nautobot API client
        subnet_id: Subnet UUID
        network_id: Parent network UUID
        tenant_id: Tenant/project UUID
        cidr: Subnet CIDR
        is_external: Whether the parent network is external (determines namespace)

    Returns:
        0 on success, 1 on failure
    """
    try:
        # External network subnets go to Global namespace
        namespace = "Global" if is_external else network_id

        payload = {
            "id": subnet_id,
            "prefix": cidr,
            "status": "Active",
            "namespace": {"name": namespace},
            "tenant": {"id": tenant_id},
        }

        # Try update first, then create
        if not _update_nautobot_prefix(nautobot, subnet_id, payload):
            _create_nautobot_prefix(nautobot, payload)

        return 0
    except Exception:
        logger.exception("Failed to sync subnet %s", subnet_id)
        return 1
