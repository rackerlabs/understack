import argparse
import json
import logging
import pathlib
import sys
from collections.abc import Callable
from typing import Any

import pynautobot
from openstack.connection import Connection
from pynautobot.core.api import Api as NautobotApi

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.openstack.client import get_openstack_client
from understack_workflows.oslo_event import ironic_node
from understack_workflows.oslo_event import ironic_port
from understack_workflows.oslo_event import ironic_portgroup
from understack_workflows.oslo_event import keystone_project
from understack_workflows.oslo_event import nautobot_device_sync
from understack_workflows.oslo_event import neutron_network
from understack_workflows.oslo_event import neutron_subnet

logger = logging.getLogger(__name__)


_EXIT_SUCCESS = 0
_EXIT_PARSE_ERROR = 5
_EXIT_NO_EVENT_HANDLER = 6
_EXIT_CLIENT_ERROR = 7
_EXIT_HANDLER_ERROR = 8


class EventParseError(Exception):
    """Raised when event data cannot be parsed or is invalid."""

    pass


class EventValidationError(Exception):
    """Raised when event structure validation fails."""

    pass


class ClientInitializationError(Exception):
    """Raised when client initialization fails."""

    pass


class EventHandlerError(Exception):
    """Raised when event handler execution fails."""

    pass


class NoEventHandlerError(Exception):
    """Raised when no handler exists for the event type."""

    pass


# Type alias for event handler functions
EventHandler = Callable[[Connection, NautobotApi, dict[str, Any]], int]

# add the event_type here and the function that should be called
_event_handlers: dict[str, EventHandler | list[EventHandler]] = {
    "baremetal.port.create.end": ironic_port.handle_port_create_update,
    "baremetal.port.update.end": ironic_port.handle_port_create_update,
    "baremetal.port.delete.end": ironic_port.handle_port_delete,
    "baremetal.portgroup.create.end": ironic_portgroup.handle_portgroup_create_update,
    "baremetal.portgroup.update.end": ironic_portgroup.handle_portgroup_create_update,
    "baremetal.portgroup.delete.end": ironic_portgroup.handle_portgroup_delete,
    "baremetal.node.update.end": nautobot_device_sync.handle_node_event,
    "baremetal.node.delete.end": nautobot_device_sync.handle_node_delete_event,
    "baremetal.node.provision_set.end": [
        ironic_node.handle_provision_end,
        nautobot_device_sync.handle_node_event,
    ],
    "identity.project.created": keystone_project.handle_project_created,
    "identity.project.updated": keystone_project.handle_project_updated,
    "identity.project.deleted": keystone_project.handle_project_deleted,
    "network.create.end": neutron_network.handle_network_create_or_update,
    "network.update.end": neutron_network.handle_network_create_or_update,
    "network.delete.end": neutron_network.handle_network_delete,
    "subnet.create.end": neutron_subnet.handle_subnet_create_or_update,
    "subnet.update.end": neutron_subnet.handle_subnet_create_or_update,
    "subnet.delete.end": neutron_subnet.handle_subnet_delete,
}


def argument_parser():
    parser = argparse.ArgumentParser(description="OpenStack Event Receiver")
    parser.add_argument(
        "--os-cloud",
        type=str,
        help="Cloud to load. default: %(default)s",
    )
    parser.add_argument(
        "--file", type=pathlib.Path, help="Read event from a file instead of stdin"
    )
    parser = parser_nautobot_args(parser)

    return parser


def read_event(file: pathlib.Path | str | None) -> dict[str, Any]:
    """Read and parse event data."""
    try:
        if file:
            logger.debug("Reading event from file: %s", file)
            if isinstance(file, str):
                file = pathlib.Path(file)
            with file.open("r") as f:
                event_data = json.load(f)
        else:
            logger.debug("Reading event from stdin")
            event_data = json.load(sys.stdin)

        logger.debug("Successfully parsed event data")
        return event_data

    except json.JSONDecodeError as e:
        raise EventParseError("Invalid JSON format") from e
    except FileNotFoundError as e:
        raise EventParseError(f"File not found: {file}") from e
    except PermissionError as e:
        raise EventParseError(f"Permission denied reading file: {file}") from e
    except Exception as e:
        raise EventParseError("Unexpected error reading event data") from e


def validate_event(event: dict[str, Any]) -> str:
    """Validate event structure and return event type."""
    event_type = event.get("event_type")
    if not event_type:
        raise EventValidationError("Event must contain 'event_type' field")

    if not isinstance(event_type, str):
        raise EventValidationError("Event type must be a string")

    logger.debug("Event validation successful, event_type: %s", event_type)
    return event_type


def initialize_clients(args: argparse.Namespace) -> tuple[Connection, NautobotApi]:
    """Initialize OpenStack and Nautobot clients."""
    try:
        logger.debug("Initializing OpenStack client with cloud: %s", args.os_cloud)
        conn = get_openstack_client(cloud=args.os_cloud)
        logger.debug("OpenStack client initialized successfully")
    except Exception as e:
        raise ClientInitializationError("Failed to initialize OpenStack client") from e

    try:
        nb_token = args.nautobot_token or credential("nb-token", "token")
        logger.debug("Initializing Nautobot client with URL: %s", args.nautobot_url)
        nautobot = pynautobot.api(args.nautobot_url, token=nb_token)
        logger.debug("Nautobot client initialized successfully")
    except Exception as e:
        raise ClientInitializationError("Failed to initialize Nautobot client") from e

    return conn, nautobot


def main() -> int:
    """Handles OpenStack events in a generic way."""
    setup_logger()
    # parse our input arguments
    args = argument_parser().parse_args()

    logger.info("Starting OpenStack event receiver")
    logger.debug("Arguments: %s", vars(args))

    # read and parse the basics of the event
    try:
        event = read_event(args.file)
    except EventParseError:
        logger.exception("Event parsing failed")
        sys.exit(_EXIT_PARSE_ERROR)
    logger.debug("Event read: %s", event)

    # validate event structure and extract event type
    try:
        event_type = validate_event(event)
    except EventValidationError as e:
        logger.error("Event validation failed: %s", e)
        sys.exit(_EXIT_PARSE_ERROR)

    logger.info("Processing event type: %s", event_type)

    # look up the event handler(s)
    event_handlers = _event_handlers.get(event_type)
    if event_handlers is None:
        logger.error("No event handler for event type: %s", event_type)
        logger.debug("Available event handlers: %s", list(_event_handlers.keys()))
        sys.exit(_EXIT_NO_EVENT_HANDLER)

    # normalize to list for consistent processing
    if not isinstance(event_handlers, list):
        event_handlers = [event_handlers]

    logger.debug(
        "Found %d handler(s) for event type: %s", len(event_handlers), event_type
    )

    # get a connection to OpenStack and to Nautobot
    try:
        conn, nautobot = initialize_clients(args)
    except ClientInitializationError:
        logger.exception("Client initialization failed")
        sys.exit(_EXIT_CLIENT_ERROR)

    # execute all event handlers
    last_ret = _EXIT_SUCCESS
    for idx, event_handler in enumerate(event_handlers, 1):
        handler_name = getattr(event_handler, "__name__", f"handler_{idx}")
        logger.info(
            "Executing handler %d/%d: %s", idx, len(event_handlers), handler_name
        )
        try:
            ret = event_handler(conn, nautobot, event)
            if isinstance(ret, int):
                last_ret = ret
            logger.info("Handler %s completed with return code: %s", handler_name, ret)
        except Exception:
            logger.exception("Handler %s failed", handler_name)
            sys.exit(_EXIT_HANDLER_ERROR)

    logger.info("All handlers completed successfully")
    return last_ret
