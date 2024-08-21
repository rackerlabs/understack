import argparse
import os
from uuid import UUID

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import Nautobot


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Update CustomField in Nautobot",
    )
    parser.add_argument(
        "--device-id", required=True, type=UUID, help="Nautobot device UUID"
    )
    parser.add_argument("--field-name", required=True)
    parser.add_argument("--field-value", required=True)
    parser = parser_nautobot_args(parser)

    return parser


logger = setup_logger(__name__)


def main():
    args = argument_parser().parse_args()

    device_uuid = args.device_id
    field_name = args.field_name
    field_value = args.field_value
    nb_token = args.nautobot_token or credential("nb-token", "token")

    nautobot = Nautobot(args.nautobot_url, nb_token, logger=logger)
    nautobot.update_cf(device_uuid, field_name, field_value)


if __name__ == "__main__":
    main()
