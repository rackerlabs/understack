import json
import sys
import argparse
import os
import pynautobot

from understack_workflows.helpers import setup_logger
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.bmc_credentials import set_bmc_password
from understack_workflows.bmc_bios import update_dell_bios_settings
from understack_workflows.bmc import bmc_for_ip_address
import understack_workflows.ironic_node
from understack_workflows.bmc_chassis_info import chassis_info
from understack_workflows import nautobot_device
from understack_workflows.helpers import credential

logger = setup_logger(__name__)

def main():
    """On-board new or Refresh existing baremetal node

    We have been invoked because a baremetal node is available.

    - connect to the BMC, trying standard password then factory default

    - ensure standard BMC password is set

    - TODO: create and install SSL certificate

    - TODO: update BMC firmware

    - TODO: set NTP Server IPs for DRAC
      (NTP server IP addresses are different per region)

    -  Using BMC, configure our standard BIOS settings
       - set PXE boot device
       - set timezone to UTC

    -  from BMC, discover basic hardware info:
       - manufacturer, model number, serial number
       - list ethernet interfaces with:
          - name like BMC or SLOT.NIC.1-1
          - MAC address
          - LLDP connections [{remote_mac, remote_interface_name}]

    - Find or create this server in Nautobot by serial number.

    - set name, manufacturer, model, serial, location, rack

    - Find BMC interface

    - Create DRAC network prefix

    - create BMC IP address assignment for BMC interface

    - For each server interface
        - find or create server interface by name in nautobot
        - set interface mac addresses
        - look up switch by mac address which is stored in asset tag field in nautobot
        - look up switch interface by name
        - find or create cable

    -  Find or create this baremetal node in Ironic
       - create ports with MACs
       - advance to available state
       - set flavor?  what else?

    """

    args = argument_parser().parse_args()

    bmc_ip_address = args.bmc_ip_address
    logger.info(f"{__file__} starting for {bmc_ip_address=}")

    url = args.nautobot_url
    token = args.nautobot_token or credential("nb-token", "token")
    nautobot = pynautobot.api(url, token=token)


    bmc = bmc_for_ip_address(bmc_ip_address, password=args.bmc_password)
    if args.bmc_password is None:
        logger.info("Setting BMC password to bmc.password")
        set_bmc_password(bmc.ip_address, bmc.password)

    # TODO: make this pseudo-idempotent by ignoring the error when a job is already scheduled:
    # update_dell_bios_settings(bmc)

    device_info = chassis_info(bmc)

    logger.info(f"Discovered {device_info}")
    device_id = nautobot_device.find_or_create(device_info, nautobot)

    # update server BMC IP address

    # get nautobot interfaces with connections for this server (graphql)
    #
    # compare with discovered connections (have nautobot get switch macs for
    # easier comparison)
    #
    # update interfaces+connections as required.  What to do about interfaces or
    # cables that disappeared?  Cables that disapperared that were in a
    # different rack?

    #_ironic_provision_state = ironic_node.create_or_update(device_uuid, bmc, logger)
    #sync_interfaces.from_nautobot_to_ironic(device_id)

    logger.info(f"{__file__} complete successfully for {bmc.ip_address}")


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__), description="Ingest Baremetal"
    )
    parser.add_argument(
        "--bmc-ip-address", type=str, required=True, help="BMC IP"
    )
    parser.add_argument(
        "--bmc-password", type=str, required=False, help="BMC Pass"
    )
    parser.add_argument(
        "--bmc-mac-address", type=str, required=False, help="BMC MAC Addr"
    )
    parser = parser_nautobot_args(parser)
    return parser

if __name__ == "__main__":
    main()
