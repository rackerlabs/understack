import argparse
import os
from uuid import UUID

from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import Nautobot


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Ironic to Nautobot provisioning state sync",
    )
    parser.add_argument(
        "--device-id", required=True, type=UUID, help="Nautobot device UUID"
    )
    parser.add_argument("--field-name", required=True)
    parser.add_argument("--field-value", required=True)
    parser.add_argument("--nautobot_url", required=False)
    parser.add_argument("--nautobot_token", required=False)

    return parser


logger = setup_logger(__name__)


def main():
    args = argument_parser().parse_args()

    default_nb_url = "http://nautobot-default.nautobot.svc.cluster.local"
    device_uuid = args.device_id
    field_name = args.field_name
    field_value = args.field_value
    nb_url = args.nautobot_url or default_nb_url
    nb_token = args.nautobot_token or credential("nb-token", "token")

    nautobot = Nautobot(nb_url, nb_token, logger=logger)
    nautobot.update_cf(device_uuid, field_name, field_value)


if __name__ == "__main__":
    main()
