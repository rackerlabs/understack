import argparse
import os
from uuid import UUID

from understack_workflows.bmc_sushy import bmc_sushy_session
from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.models import Chassis
from understack_workflows.nautobot import Nautobot

logger = setup_logger(__name__)


def is_off_board(interface):
    return "Embedded ALOM" in interface.location or "Embedded" not in interface.location

def argument_parser(name):
    parser = argparse.ArgumentParser(
        prog=os.path.basename(name), description="Nautobot Interface sync"
    )
    parser.add_argument(
        "--device-id", type=UUID, required=True, help="Nautobot device ID"
    )
    parser = parser_nautobot_args(parser)
    return parser


def do_sync(device_id: UUID, nautobot: Nautobot):
    bmc_ip = nautobot.device_bmc_ip(device_id)
    bmc = bmc_sushy_session(bmc_ip)
    chassis = Chassis.from_redfish(bmc)

    interfaces = [
        interface for interface in chassis.network_interfaces if is_off_board(interface)
    ]

    nautobot.bulk_create_interfaces(device_id, interfaces)


def main():
    """Discover interface names via redfish, add relevant ones to Nautobot."""
    parser = argument_parser(__file__)
    args = parser.parse_args()

    nb_token = args.nautobot_token or credential("nb-token", "token")
    nautobot = Nautobot(args.nautobot_url, nb_token, logger=logger)

    do_sync(args.device_id, nautobot)


if __name__ == "__main__":
    main()
