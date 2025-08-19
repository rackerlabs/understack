import argparse
import json
import pathlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pynautobot
from openstack.connection import Connection
from pynautobot.core.api import Api as NautobotApi

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.openstack.client import get_openstack_client
from understack_workflows.oslo_event import ironic_port
from understack_workflows.oslo_event import keystone_project
from understack_workflows.oslo_event.notifiers.amqp_cinder_sa import (
    StorageAutomationNotifier,
)

logger = setup_logger(__name__)


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
@dataclass
class HandlerResult:
    exit_code: int
    message: str | dict[str, Any] | None = None


EventHandler = Callable[[Connection, NautobotApi, dict[str, Any]], HandlerResult]
# add the event_type here and the function that should be called
_event_handlers: dict[str, EventHandler] = {
    "baremetal.port.create.end": ironic_port.handle_port_create_update,
    "baremetal.port.update.end": ironic_port.handle_port_create_update,
    "baremetal.port.delete.end": ironic_port.handle_port_delete,
    "identity.project.created": keystone_project.handle_project_created,
}

_result_notifiers = {"identity.project.created": StorageAutomationNotifier()}


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
    # parse our input arguments
    args = argument_parser().parse_args()

    logger.info("Starting OpenStack event receiver")
    logger.debug("Arguments: %s", args)

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

    # look up the event handler
    event_handler = _event_handlers.get(event_type)
    if event_handler is None:
        logger.error("No event handler for event type: %s", event_type)
        logger.debug("Available event handlers: %s", list(_event_handlers.keys()))
        sys.exit(_EXIT_NO_EVENT_HANDLER)

    logger.debug("Found event handler for event type: %s", event_type)

    # get a connection to OpenStack and to Nautobot
    try:
        conn, nautobot = initialize_clients(args)
    except ClientInitializationError:
        logger.exception("Client initialization failed")
        sys.exit(_EXIT_CLIENT_ERROR)

    # execute the event handler
    logger.info("Executing event handler for event type: %s", event_type)
    try:
        ret = event_handler(conn, nautobot, event)
    except Exception:
        logger.exception("Event handler failed")
        sys.exit(_EXIT_HANDLER_ERROR)

    logger.info(
        "Event handler completed successfully with return code: %s", ret.exit_code
    )

    try:
        notifier = _result_notifiers[event_type]
        if notifier:
            notifier.publish(event, event_type, ret)
    except Exception:
        logger.exception("Result notifier failed")
        sys.exit(_EXIT_HANDLER_ERROR)

    # exit if the event handler provided a return code or just with success
    if isinstance(ret, int):
        return ret
    return _EXIT_SUCCESS
