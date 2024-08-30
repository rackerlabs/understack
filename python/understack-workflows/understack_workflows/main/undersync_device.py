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

network_name_status = {
    "tenant": "Active",
    "provisioning": "Provisioning Interface"
}

def update_nautobot(args) -> UUID:
    device_id = args.device_id
    interface_id = args.interface_id
    network_name = args.network_name

    nb_url = args.nautobot_url
    nb_token = args.nautobot_token or credential("nb-token", "token")

    new_status = network_name_status[args.network_name]

    nautobot = Nautobot(nb_url, nb_token, logger=logger)
    logger.info(f"Updating Nautobot {device_id=!s} {interface_id=!s} {network_name=}")
    interface = nautobot.update_switch_interface_status(interface_id, new_status)
    logger.info(f"Updated Nautobot {device_id=!s} {interface_id=!s} {network_name=}")

    switch_id = interface.device.id
    logger.info(f"Interface connected to switch {switch_id!s}")
    return switch_id


def call_undersync(args, switch_id: UUID):
    undersync_token = credential("undersync", "token")
    if not undersync_token:
        logger.error("Please provide auth token for Undersync.")
        sys.exit(1)
    undersync = Undersync(undersync_token)

    try:
        return undersync.sync_devices([switch_id], dry_run=args.dry_run, force=args.force)
    except Exception as error:
        logger.error(error)
        sys.exit(2)


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Trigger undersync run for a device",
    )
    parser.add_argument(
        "--interface-id", type=UUID, required=True, help="Nautobot interface UUID"
    )
    parser.add_argument(
        "--device-id", type=UUID, required=False, help="Nautobot device UUID"
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

    switch_id = update_nautobot(args)
    response = call_undersync(args, switch_id)
    logger.info(f"Undersync returned: {response.json()}")


if __name__ == "__main__":
    main()
