import argparse
import os
import sys
from uuid import UUID
import requests

from understack_workflows.helpers import boolean_args
from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot import Nautobot
from understack_workflows.undersync.client import Undersync

logger = setup_logger(__name__)


def update_nautobot(args) -> UUID:
    device_id = args.device_id
    interface_mac = args.interface_mac
    network_name = args.network_name

    nb_url = args.nautobot_url
    nb_token = args.nautobot_token or credential("nb-token", "token")

    logger.info(f"Updating Nautobot {device_id=!s} {interface_mac=!s} {network_name=}")

    if network_name == "tenant":
        switch_id = update_nautobot_for_tenant(
            nb_url, nb_token, interface_mac, args.network_id
        )
    elif network_name == "provisioning":
        switch_id = update_nautobot_for_provisioning(
            nb_url, nb_token, device_id, interface_mac
        )
    else:
        raise ValueError(f"need provisioning or tenant, not {network_name=}")

    logger.info(f"Updated Nautobot {device_id=!s} {interface_mac=!s} {network_name=}")

    logger.info(f"Interface connected to switch {switch_id!s}")
    return switch_id


def update_nautobot_for_provisioning(
    nb_url, nb_token, device_id: UUID, interface_mac: str
):
    new_status = "Provisioning-Interface"
    nautobot = Nautobot(nb_url, nb_token, logger=logger)

    interface = nautobot.update_switch_interface_status(
        device_id, interface_mac, new_status
    )
    switch_id = interface.device.id
    return switch_id


def update_nautobot_for_tenant(
    nb_url, nb_token, server_interface_mac: str, ucvni_id: UUID
) -> UUID:
    """Runs a Nautobot Job to update a switch interface for tenant mode

    The nautobot job will assign vlans as required and set the interface
    into the correct mode for "normal" tenant operation.

    The switch ID is returned.
    """

    # Making this http request directly because it was not clear how to get
    # the pynautobot api client to call an arbitrary endpoint:

    uri = f"{nb_url}/api/plugins/undercloud-vni/ucvni_jobs/prep_switch_interface"
    payload = {
        "ucvni_id": str(ucvni_id),
        "server_interface_mac": str(server_interface_mac),
    }
    headers = {
        "Authorization": f"Token {nb_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    logger.debug(f"Running Nautobot prep_switch_interface job {uri=} {payload=}")

    response = requests.request("POST", uri, headers=headers, json=payload)
    response.raise_for_status()
    response = response.json()
    logger.debug(f"Nautobot prep_switch_interface job {response=}")

    return response["switch_id"]


def call_undersync(args, switch_id: UUID):
    undersync_token = credential("undersync", "token")
    if not undersync_token:
        logger.error("Please provide auth token for Undersync.")
        sys.exit(1)
    undersync = Undersync(undersync_token)

    try:
        return undersync.sync_devices(
            [str(switch_id)], dry_run=args.dry_run, force=args.force
        )
    except Exception as error:
        logger.error(error)
        sys.exit(2)


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Trigger undersync run for a device",
    )
    parser.add_argument(
        "--interface-mac", type=str, required=True, help="Interface MAC address"
    )
    parser.add_argument(
        "--device-id", type=UUID, required=False, help="Nautobot device UUID"
    )
    parser.add_argument("--network-name", required=True)
    parser.add_argument(
        "--network-id", type=UUID, required=True, help="Nautobot network UUID"
    )
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
    """Updates Interface Status in Nautobot and triggers Undersync.

    Updates Nautobot Device Interface status field and follows with
    request to Undersync service, requesting sync for all of the
    uplink_switches that the device is connected to.
    """
    args = argument_parser().parse_args()

    switch_id = update_nautobot(args)
    response = call_undersync(args, switch_id)
    logger.info(f"Undersync returned: {response.json()}")


if __name__ == "__main__":
    main()
