import argparse
import logging
import uuid
from enum import StrEnum

import openstack
from openstack.connection import Connection

from understack_workflows.domain import DefaultDomain
from understack_workflows.domain import domain_id
from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import Nautobot

logger = setup_logger(__name__, level=logging.INFO)


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
    project = conn.identity.get_project(project_id.hex)
    ret = project.domain_id == only_domain.hex
    if not ret:
        logger.info(
            f"keystone project {project_id!s} part of domain "
            f"{project.domain_id} and not {only_domain!s}"
        )
    return ret


def handle_project_create(conn: Connection, nautobot: Nautobot, project_id: uuid.UUID):
    logger.info(f"got request to create tenant {project_id!s}")
    project = conn.identity.get_project(project_id.hex)
    ten_api = nautobot.session.tenancy.tenants
    ten_api.url = f"{ten_api.base_url}/plugins/uuid-api-endpoints/tenant"
    ten = ten_api.create(
        id=str(project_id), name=project.name, description=project.description
    )
    logger.info(f"tenant '{project_id!s}' created {ten.created}")


def handle_project_update(conn: Connection, nautobot: Nautobot, project_id: uuid.UUID):
    logger.info(f"got request to update tenant {project_id!s}")
    project = conn.identity.get_project(project_id.hex)
    ten = nautobot.session.tenancy.tenants.get(project_id)
    ten.description = project.description
    ten.save()
    logger.info(f"tenant '{project_id!s}' last updated {ten.last_updated}")


def handle_project_delete(conn: Connection, nautobot: Nautobot, project_id: uuid.UUID):
    logger.info(f"got request to delete tenant {project_id!s}")
    ten = nautobot.session.tenancy.tenants.get(project_id)
    if not ten:
        logger.warn(f"tenant '{project_id!s}' does not exist already")
        return
    ten.delete()
    logger.info(f"deleted tenant {project_id!s}")


def do_action(
    conn: Connection,
    nautobot: Nautobot,
    event: Event,
    project_id: uuid.UUID,
    only_domain: uuid.UUID | DefaultDomain | None,
):
    if event in [Event.ProjectCreate, Event.ProjectUpdate] and not is_valid_domain(
        conn, project_id, only_domain
    ):
        logger.info(
            f"keystone project {project_id!s} not part of {only_domain!s}, skipping"
        )
        return

    match event:
        case Event.ProjectCreate:
            handle_project_create(conn, nautobot, project_id)
        case Event.ProjectUpdate:
            handle_project_update(conn, nautobot, project_id)
        case Event.ProjectDelete:
            handle_project_delete(conn, nautobot, project_id)
        case _:
            raise Exception(f"Cannot handle event: {event}")


def main():
    args = argument_parser().parse_args()

    conn = openstack.connect(cloud=args.os_cloud)
    nb_token = args.nautobot_token or credential("nb-token", "token")
    nautobot = Nautobot(args.nautobot_url, nb_token, logger=logger)

    do_action(conn, nautobot, args.event, args.object, args.only_domain)
