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

OUTSIDE_NETWORK_NAME = "OUTSIDE"


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
            "keystone project %s part of domain %s and not %s",
            project_id,
            project.domain_id,
            only_domain,
        )
    return ret


def _create_outside_network(conn: Connection, project_id: uuid.UUID):
    payload = _outside_network_payload(project_id)
    network = conn.network.find_network(**payload)
    if network:
        logger.info(
            "%s Network %s already exists for this tenant",
            OUTSIDE_NETWORK_NAME,
            network.id,
        )
    else:
        payload.update(name=payload.pop("name_or_id"))
        network = conn.network.create_network(**payload)
        logger.info(
            "Created %s Network %s for tenant", OUTSIDE_NETWORK_NAME, network.id
        )


def _delete_outside_network(conn: Connection, project_id: uuid.UUID):
    payload = _outside_network_payload(project_id)
    network = conn.network.find_network(**payload)
    if network:
        conn.delete_network(network.id)
        logger.info(
            "Deleted %s Network %s for this tenant", OUTSIDE_NETWORK_NAME, network.id
        )


def _outside_network_payload(project_id: uuid.UUID) -> dict:
    return {
        "project_id": project_id,
        "name_or_id": OUTSIDE_NETWORK_NAME,
        "router:external": True,
    }


def handle_project_create(
    conn: Connection, nautobot: Nautobot, project_id: uuid.UUID
) -> int:
    logger.info("got request to create tenant %s", project_id)
    project = conn.identity.get_project(project_id.hex)  # type: ignore
    ten_api = nautobot.session.tenancy.tenants
    try:
        ten = ten_api.create(
            id=str(project_id), name=project.name, description=project.description
        )
        _create_outside_network(conn, project_id)
    except Exception:
        logger.exception(
            "Unable to create project %s / %s", str(project_id), project.name
        )
        return _EXIT_API_ERROR

    logger.info("tenant %s created %s", project_id, ten.created)  # type: ignore
    return _EXIT_SUCCESS


def handle_project_update(
    conn: Connection, nautobot: Nautobot, project_id: uuid.UUID
) -> int:
    logger.info("got request to update tenant %s", project_id)
    project = conn.identity.get_project(project_id.hex)  # type: ignore
    tenant_api = nautobot.session.tenancy.tenants

    existing_tenant = tenant_api.get(project_id)
    logger.info("existing_tenant: %s", existing_tenant)
    try:
        if existing_tenant is None:
            new_tenant = tenant_api.create(
                id=str(project_id), name=project.name, description=project.description
            )
            logger.info("tenant %s created %s", project_id, new_tenant.created)  # type: ignore
        else:
            existing_tenant.description = project.description  # type: ignore
            existing_tenant.save()  # type: ignore
            logger.info(
                "tenant %s last updated %s",
                project_id,
                existing_tenant.last_updated,  # type: ignore
            )

        _create_outside_network(conn, project_id)
    except Exception:
        logger.exception(
            "Unable to update project %s / %s", str(project_id), project.name
        )
        return _EXIT_API_ERROR
    return _EXIT_SUCCESS


def handle_project_delete(
    conn: Connection, nautobot: Nautobot, project_id: uuid.UUID
) -> int:
    logger.info("got request to delete tenant %s", project_id)
    ten = nautobot.session.tenancy.tenants.get(project_id)
    if not ten:
        logger.warning("tenant %s does not exist, nothing to delete", project_id)
        return _EXIT_SUCCESS

    _delete_outside_network(conn, project_id)
    ten.delete()  # type: ignore
    logger.info("deleted tenant %s", project_id)
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
            "keystone project %s not part of %s, skipping", project_id, only_domain
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
