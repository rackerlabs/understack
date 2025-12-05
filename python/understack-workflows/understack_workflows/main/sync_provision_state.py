import argparse
import os
from uuid import UUID

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.provision_state_mapper import ProvisionStateMapper
from understack_workflows.nautobot import Nautobot


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Synchronize Ironic provision_state to Nautobot",
    )
    parser.add_argument(
        "--device-id", required=True, type=UUID, help="Nautobot device UUID"
    )
    parser.add_argument("--provision-state", required=True)
    parser.add_argument("--lessee")
    parser.add_argument("--resource-class")
    parser = parser_nautobot_args(parser)

    return parser


logger = setup_logger(__name__)


def do_action(
    nautobot,
    device_uuid,
    provision_state,
    tenant_id=None,
    resource_class=None,
):
    new_status = ProvisionStateMapper.translate_to_nautobot(provision_state)

    custom_fields_to_update = {
        "ironic_provision_state": provision_state,
        "resource_class": resource_class,
    }

    if new_status:
        nautobot.update_cf(
            device_id=device_uuid, tenant_id=tenant_id, fields=custom_fields_to_update
        )
        nautobot.update_device_status(device_uuid, new_status)


def main():
    args = argument_parser().parse_args()

    device_uuid = args.device_id
    tenant_id = None
    if args.lessee:
        try:
            tenant_id = UUID(args.lessee)
        except ValueError:
            logger.warning("Invalid UUID format for lessee: %s", args.lessee)
    nb_token = args.nautobot_token or credential("nb-token", "token")

    nautobot = Nautobot(args.nautobot_url, nb_token, logger=logger)
    do_action(
        nautobot,
        device_uuid=device_uuid,
        provision_state=args.provision_state,
        tenant_id=tenant_id,
        resource_class=args.resource_class,
    )


if __name__ == "__main__":
    main()
