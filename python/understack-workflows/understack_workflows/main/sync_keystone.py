import argparse
import logging
import uuid
from collections.abc import Sequence
from enum import StrEnum
from typing import cast

import pynautobot
from pynautobot.core.response import Record

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.openstack.client import Connection
from understack_workflows.openstack.client import get_openstack_client

logger = setup_logger(__name__, level=logging.INFO)


_EXIT_SUCCESS = 0
_EXIT_API_ERROR = 1
_EXIT_EVENT_UNKNOWN = 2


class Event(StrEnum):
    ProjectCreate = "identity.project.created"
    ProjectUpdate = "identity.project.updated"
    ProjectDelete = "identity.project.deleted"


def argument_parser():
    parser = argparse.ArgumentParser(
        description="Handle Keystone Events",
    )
    parser.add_argument(
        "--os-cloud",
        type=str,
        default="understack",
        help="Cloud to load. default: %(default)s",
    )

    parser.add_argument("event", type=Event, choices=[item.value for item in Event])
    parser.add_argument(
        "object", type=uuid.UUID, help="Keystone ID of object the event happened on"
    )
    parser = parser_nautobot_args(parser)

    return parser


def _tenant_attrs(conn: Connection, project_id: uuid.UUID) -> tuple[str, str]:
    project = conn.identity.get_project(project_id.hex)  # type: ignore
    domain_id = project.domain_id
    is_default_domain = domain_id == "default"

    if is_default_domain:
        domain_name = "default"
    else:
        domain = conn.identity.get_project(domain_id)  # type: ignore
        domain_name = domain.name

    tenant_name = f"{domain_name}:{project.name}"
    return tenant_name, str(project.description)


def _unmap_tenant_from_devices(
    tenant_id: uuid.UUID,
    nautobot: pynautobot.api,
):
    devices: Sequence[Record] = list(nautobot.dcim.devices.filter(tenant=tenant_id))
    for d in devices:
        d.tenant = None  # type: ignore[attr-defined]
        nautobot.dcim.devices.update(devices)


def handle_project_create(
    conn: Connection, nautobot: pynautobot.api, project_id: uuid.UUID
) -> int:
    logger.info("got request to create tenant %s", project_id.hex)
    tenant_name, tenant_description = _tenant_attrs(conn, project_id)

    try:
        tenant = nautobot.tenancy.tenants.create(
            id=str(project_id), name=tenant_name, description=tenant_description
        )
    except Exception:
        logger.exception(
            "Unable to create project %s / %s", str(project_id), tenant_name
        )
        return _EXIT_API_ERROR

    logger.info("tenant %s created %s", project_id, tenant.created)  # type: ignore
    return _EXIT_SUCCESS


def handle_project_update(
    conn: Connection, nautobot: pynautobot.api, project_id: uuid.UUID
) -> int:
    logger.info("got request to update tenant %s", project_id.hex)
    tenant_name, tenant_description = _tenant_attrs(conn, project_id)

    existing_tenant = nautobot.tenancy.tenants.get(id=project_id)
    logger.info("existing_tenant: %s", existing_tenant)
    try:
        if existing_tenant is None:
            new_tenant = nautobot.tenancy.tenants.create(
                id=str(project_id), name=tenant_name, description=tenant_description
            )
            logger.info("tenant %s created %s", project_id, new_tenant.created)  # type: ignore
        else:
            existing_tenant = cast(Record, existing_tenant)
            existing_tenant.update(
                {"name": tenant_name, "description": tenant_description}
            )  # type: ignore
            logger.info(
                "tenant %s last updated %s",
                project_id,
                existing_tenant.last_updated,  # type: ignore
            )

    except Exception:
        logger.exception(
            "Unable to update project %s / %s", str(project_id), tenant_name
        )
        return _EXIT_API_ERROR
    return _EXIT_SUCCESS


def handle_project_delete(
    conn: Connection, nautobot: pynautobot.api, project_id: uuid.UUID
) -> int:
    logger.info("got request to delete tenant %s", project_id)
    tenant = nautobot.tenancy.tenants.get(id=project_id)
    if not tenant:
        logger.warning("tenant %s does not exist, nothing to delete", project_id)
        return _EXIT_SUCCESS

    _unmap_tenant_from_devices(tenant_id=project_id, nautobot=nautobot)

    tenant = cast(Record, tenant)
    tenant.delete()
    logger.info("deleted tenant %s", project_id)
    return _EXIT_SUCCESS


def do_action(
    conn: Connection,
    nautobot: pynautobot.api,
    event: Event,
    project_id: uuid.UUID,
) -> int:
    match event:
        case Event.ProjectCreate:
            return handle_project_create(conn, nautobot, project_id)
        case Event.ProjectUpdate:
            return handle_project_update(conn, nautobot, project_id)
        case Event.ProjectDelete:
            return handle_project_delete(conn, nautobot, project_id)
        case _:
            logger.error("Cannot handle event: %s", event)
            return _EXIT_EVENT_UNKNOWN
    return _EXIT_EVENT_UNKNOWN


def main() -> int:
    args = argument_parser().parse_args()

    conn = get_openstack_client(cloud=args.os_cloud)
    nb_token = args.nautobot_token or credential("nb-token", "token")
    nautobot = pynautobot.api(args.nautobot_url, token=nb_token)
    return do_action(conn, nautobot, args.event, args.object)
