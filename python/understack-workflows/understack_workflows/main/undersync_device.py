import argparse
import os
import sys
from uuid import UUID

from understack_workflows.helpers import boolean_args
from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import Nautobot
from understack_workflows.undersync.client import Undersync

logger = setup_logger(__name__)


def update_nautobot(args) -> list[str]:
    device_uuid = args.device_id
    field_name = "connected_to_network"
    field_value = args.network_name
    nb_url = args.nautobot_url

    nb_token = args.nautobot_token or credential("nb-token", "token")
    nautobot = Nautobot(nb_url, nb_token, logger=logger)
    logger.info(
        f"Updating Device {device_uuid} and moving it to '{field_value}' network."
    )
    nautobot.update_cf(device_uuid, field_name, field_value)
    logger.debug(f"Updated Device.{field_name} to {field_value}")
    switches = nautobot.uplink_switches(device_uuid)
    logger.info(f"Obtained switch IDs: {switches}")
    return switches


def call_undersync(args, switches):
    undersync_token = credential("undersync", "token")
    if not undersync_token:
        logger.error("Please provide auth token for Undersync.")
        sys.exit(1)
    undersync = Undersync(undersync_token)

    try:
        return undersync.sync_devices(switches, dry_run=args.dry_run, force=args.force)
    except Exception as error:
        logger.error(error)
        sys.exit(2)


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Trigger undersync run for a device",
    )
    parser.add_argument(
        "--device-id", type=UUID, required=True, help="Nautobot device UUID"
    )
    parser.add_argument("--network-name", required=True)
    parser = parser_nautobot_args(parser)
    parser.add_argument(
        "--force",
        type=boolean_args,
        help="Call Undersync's force endpoint",
        required=False,
    )
    parser.add_argument(
        "--dry-run",
        type=boolean_args,
        help="Call Undersync's dry-run endpoint",
        required=False,
    )

    return parser


def main():
    """Updates connected_to_network and triggers Undersync.

    Updates Nautobot Device's 'connected_to_network' field and follows with
    request to Undersync service, requesting sync for all of the
    uplink_switches that the device is connected to.
    """
    args = argument_parser().parse_args()

    switches = update_nautobot(args)
    response = call_undersync(args, switches)
    logger.info(f"Undersync returned: {response.json()}")


if __name__ == "__main__":
    main()
