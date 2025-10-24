import argparse
import json
import pathlib
import sys
from typing import Any

import pynautobot
from pynautobot.core.api import Api as Nautobot

from understack_workflows import nautobot_device
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.ironic.inventory import get_device_info
from understack_workflows.openstack.client import get_ironic_client

logger = setup_logger(__name__)


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
    """Read and parse event data from file or stdin."""
    if file:
        if isinstance(file, str):
            file = pathlib.Path(file)
        with file.open("r") as f:
            return json.load(f)
    return json.load(sys.stdin)


def get_event_type(event: dict[str, Any]) -> str:
    """Extract and validate event type from event data."""
    event_type = event.get("event_type")
    if not event_type or not isinstance(event_type, str):
        raise ValueError("Event must contain 'event_type' string field")
    return event_type


def initialize_clients(args: argparse.Namespace) -> tuple[Nautobot, IronicClient]:
    """Initialize Ironic and Nautobot clients."""
    conn = get_ironic_client(cloud=args.os_cloud)
    ironic_client = IronicClient(conn)

    nb_token = args.nautobot_token or credential("nb-token", "token")
    nautobot = pynautobot.api(args.nautobot_url, token=nb_token)

    return nautobot, ironic_client


def handle_provision_end(
    nautobot: Nautobot, ironic_client: IronicClient, event_data: dict
) -> None:
    """Handle Ironic node provisioning END event."""
    payload = event_data.get("payload", {})
    payload_data = payload.get("ironic_object.data")

    if not payload_data:
        raise ValueError("Missing 'ironic_object.data' in event payload")

    node_inventory = ironic_client.get_node_inventory(node_ident=payload_data["uuid"])
    device_info: ChassisInfo = get_device_info(node_inventory)
    nb_device = nautobot_device.find_or_create(device_info, nautobot)

    logger.info("Updated Nautobot device: %s", nb_device)


EVENT_HANDLERS = {
    "baremetal.node.provision_set.end": handle_provision_end,
}


def main() -> int:
    """Process OpenStack events and update Nautobot."""
    args = argument_parser().parse_args()

    try:
        event = read_event(args.file)
        event_type = get_event_type(event)

        logger.info("Processing event: %s", event_type)

        handler = EVENT_HANDLERS.get(event_type)
        if not handler:
            logger.error("No handler for event type: %s", event_type)
            logger.info("Available handlers: %s", list(EVENT_HANDLERS.keys()))
            return 1

        nautobot, ironic_client = initialize_clients(args)
        handler(nautobot, ironic_client, event)

        logger.info("Event processed successfully")
        return 0

    except Exception:
        logger.exception("Failed to process event")
        return 1
