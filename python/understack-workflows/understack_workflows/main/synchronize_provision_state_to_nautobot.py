import argparse
import os
from uuid import UUID

from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.provision_state_mapper import ProvisioningStatusMapper
from understack_workflows.nautobot import Nautobot


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Synchronize Ironic provisioning_state to Nautobot",
    )
    parser.add_argument(
        "--device-id", required=True, type=UUID, help="Nautobot device UUID"
    )
    parser.add_argument("--provisioning-state", required=True)
    parser.add_argument("--nautobot_url", required=False)
    parser.add_argument("--nautobot_token", required=False)

    return parser


logger = setup_logger(__name__)

def do_action(nautobot, device_uuid, provision_state):
    new_status = ProvisioningStatusMapper.translate_to_nautobot(provision_state)
    nautobot.update_cf(device_uuid, 'ironic_provision_state', provision_state)
    if new_status:
        nautobot.update_device_status(device_uuid, new_status)


def main():
    args = argument_parser().parse_args()

    default_nb_url = "http://nautobot-default.nautobot.svc.cluster.local"
    device_uuid = args.device_id
    nb_url = args.nautobot_url or default_nb_url
    nb_token = args.nautobot_token or credential("nb-token", "token")

    nautobot = Nautobot(nb_url, nb_token, logger=logger)
    do_action(nautobot, device_uuid, args.provisioning_state)


if __name__ == "__main__":
    main()
