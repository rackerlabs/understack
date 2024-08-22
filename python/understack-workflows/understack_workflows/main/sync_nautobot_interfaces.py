import argparse
import os
from uuid import UUID

from understack_workflows.helpers import credential
from understack_workflows.helpers import is_off_board
from understack_workflows.helpers import oob_sushy_session
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.models import Chassis
from understack_workflows.nautobot import Nautobot

logger = setup_logger(__name__)


def argument_parser(name):
    parser = argparse.ArgumentParser(
        prog=os.path.basename(name), description="Nautobot Interface sync"
    )
    parser.add_argument(
        "--device-id", type=UUID, required=True, help="Nautobot device ID"
    )
    parser.add_argument("--oob_username", required=False, help="OOB username")
    parser.add_argument("--oob_password", required=False, help="OOB password")
    parser = parser_nautobot_args(parser)
    return parser


def do_sync(device_id: UUID, nautobot: Nautobot, bmc_user: str, bmc_pass: str):
    oob_ip = nautobot.device_oob_ip(device_id)
    oob = oob_sushy_session(oob_ip, bmc_user, bmc_pass)

    chassis = Chassis.from_redfish(oob)

    interfaces = [
        interface for interface in chassis.network_interfaces if is_off_board(interface)
    ]

    nautobot.bulk_create_interfaces(device_id, interfaces)


def main():
    parser = argument_parser(__file__)
    args = parser.parse_args()

    nb_token = args.nautobot_token or credential("nb-token", "token")
    bmc_user = args.oob_username or credential("oob-secrets", "username")
    bmc_pass = args.oob_password or credential("oob-secrets", "password")
    nautobot = Nautobot(args.nautobot_url, nb_token, logger=logger)

    do_sync(args.device_id, nautobot, bmc_user, bmc_pass)


if __name__ == "__main__":
    main()
