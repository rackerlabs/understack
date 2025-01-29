import argparse
import logging
import uuid
from enum import StrEnum

from understack_workflows.domain import DefaultDomain
from understack_workflows.domain import domain_id
from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import Nautobot
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

    parser.add_argument(
        "--only-domain",
        type=domain_id,
        help="Only operate on projects from specified domain",
    )
    parser.add_argument("event", type=Event, choices=[item.value for item in Event])
    parser.add_argument(
        "object", type=uuid.UUID, help="Keystone ID of object the event happened on"
    )
    parser = parser_nautobot_args(parser)

    return parser


def is_valid_domain(
    conn: Connection,
    project_id: uuid.UUID,
    only_domain: uuid.UUID | DefaultDomain | None,
) -> bool:
    if only_domain is None:
        return True
    project = conn.identity.get_project(project_id.hex)  # type: ignore
    ret = project.domain_id == only_domain.hex
    if not ret:
        logger.info(
            f"keystone project {project_id!s} part of domain "
            f"{project.domain_id} and not {only_domain!s}"
        )
    return ret


def handle_project_create(
    conn: Connection, nautobot: Nautobot, project_id: uuid.UUID
) -> int:
    logger.info(f"got request to create tenant {project_id!s}")
    project = conn.identity.get_project(project_id.hex)  # type: ignore
    ten_api = nautobot.session.tenancy.tenants
    try:
        ten = ten_api.create(
            id=str(project_id), name=project.name, description=project.description
        )
    except Exception:
        logger.exception(
            "Unable to create project %s / %s", str(project_id), project.name
        )
        return _EXIT_API_ERROR

    logger.info(f"tenant '{project_id!s}' created {ten.created}")  # type: ignore
    return _EXIT_SUCCESS


def handle_project_update(
    conn: Connection, nautobot: Nautobot, project_id: uuid.UUID
) -> int:
    logger.info(f"got request to update tenant {project_id!s}")
    project = conn.identity.get_project(project_id.hex)  # type: ignore
    tenant_api = nautobot.session.tenancy.tenants

    existing_tenant = tenant_api.get(project_id)
    logger.info(f"existing_tenant: {existing_tenant}")
    try:
        if existing_tenant is None:
            new_tenant = tenant_api.create(
                id=str(project_id), name=project.name, description=project.description
            )
            logger.info(f"tenant '{project_id!s}' created {new_tenant.created}")  # type: ignore
        else:
            existing_tenant.description = project.description  # type: ignore
            existing_tenant.save()  # type: ignore
            logger.info(
                f"tenant '{project_id!s}' last updated {existing_tenant.last_updated}"  # type: ignore
            )
    except Exception:
        logger.exception(
            "Unable to update project %s / %s", str(project_id), project.name
        )
        return _EXIT_API_ERROR
    return _EXIT_SUCCESS


def handle_project_delete(
    conn: Connection, nautobot: Nautobot, project_id: uuid.UUID
) -> int:
    logger.info(f"got request to delete tenant {project_id!s}")
    ten = nautobot.session.tenancy.tenants.get(project_id)
    if not ten:
        logger.warn(f"tenant '{project_id!s}' does not exist, nothing to delete")
        return _EXIT_SUCCESS
    ten.delete()  # type: ignore
    logger.info(f"deleted tenant {project_id!s}")
    return _EXIT_SUCCESS


def do_action(
    conn: Connection,
    nautobot: Nautobot,
    event: Event,
    project_id: uuid.UUID,
    only_domain: uuid.UUID | DefaultDomain | None,
) -> int:
    if event in [Event.ProjectCreate, Event.ProjectUpdate] and not is_valid_domain(
        conn, project_id, only_domain
    ):
        logger.info(
            f"keystone project {project_id!s} not part of {only_domain!s}, skipping"
        )
        return _EXIT_SUCCESS

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
    nautobot = Nautobot(args.nautobot_url, nb_token, logger=logger)

    return do_action(conn, nautobot, args.event, args.object, args.only_domain)
