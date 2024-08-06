import argparse
import os
from uuid import UUID

from understack_workflows.helpers import credential
from understack_workflows.helpers import is_off_board
from understack_workflows.helpers import oob_sushy_session
from understack_workflows.helpers import setup_logger
from understack_workflows.models import Chassis
from understack_workflows.nautobot import Nautobot

logger = setup_logger(__name__)

DEFAULT_NB_URL = "http://nautobot-default.nautobot.svc.cluster.local"


def argument_parser(name):
    parser = argparse.ArgumentParser(
        prog=os.path.basename(name), description="Nautobot Interface sync"
    )
    parser.add_argument(
        "--device-id", type=UUID, required=True, help="Nautobot device ID"
    )
    parser.add_argument("--oob_username", required=False, help="OOB username")
    parser.add_argument("--oob_password", required=False, help="OOB password")
    parser.add_argument(
        "--nautobot_url",
        required=False,
        help="Nautobot API %(default)s",
        default=DEFAULT_NB_URL,
    )
    parser.add_argument("--nautobot_token", required=False)
    return parser


def do_sync(device_id: UUID, nb_url: str, nb_token: str, bmc_user: str, bmc_pass: str):
    nautobot = Nautobot(nb_url, nb_token, logger=logger)
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

    do_sync(args.device_id, args.nautobot_url, nb_token, bmc_user, bmc_pass)


if __name__ == "__main__":
    main()
