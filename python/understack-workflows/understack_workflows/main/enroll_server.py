# pylint: disable=E1131,C0103

import argparse
import logging
import os
from pprint import pformat

from understack_workflows import ironic_node
from understack_workflows.bmc import Bmc
from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.bmc_chassis_info import chassis_info
from understack_workflows.bmc_credentials import set_bmc_password
from understack_workflows.bmc_hostname import bmc_set_hostname
from understack_workflows.bmc_settings import update_dell_drac_settings
from understack_workflows.helpers import setup_logger

logger = logging.getLogger(__name__)


def main():
    """On-board new or Refresh existing baremetal node.

    - connect to the BMC using standard password, if that fails then use
      password supplied in --old-bmc-password option, or factory default

    - ensure standard BMC password is set

    - if DHCP, set permanent IP address, netmask, default gw

    - TODO: create and install SSL certificate

    - TODO: set NTP Server IPs for DRAC
      (NTP server IP addresses are different per region)

    -  Using BMC, configure our standard BIOS settings
       - set PXE boot device
       - set timezone to UTC
       - set the hostname

    -  from BMC, discover basic hardware info:
       - manufacturer, model number, serial number
       - CPU model(s), RAM size and local storage
       - list ethernet interfaces with:
          - name like BMC or SLOT.NIC.1-1
          - MAC address
          - LLDP connections [{remote_mac, remote_interface_name}]

    - Find or create this baremetal node in Ironic
      - set the name to "{manufacturer}-{servicetag}"
      - set the driver as appropriate
    """
    setup_logger()
    args = argument_parser().parse_args()

    bmc_ip_address = args.bmc_ip_address
    logger.info("%s starting for bmc_ip_address=%s", __file__, bmc_ip_address)

    bmc = bmc_for_ip_address(bmc_ip_address)

    device_id = enroll_server(bmc, args.old_bmc_password)

    # argo workflows captures stdout as the results which we can use
    # to return the device UUID
    print(device_id)


def enroll_server(bmc: Bmc, old_password: str | None) -> str:
    """Enroll BMC to Undercloud Ironic."""
    set_bmc_password(
        ip_address=bmc.ip_address,
        new_password=bmc.password,
        old_password=old_password,
    )

    device_info = chassis_info(bmc)
    logger.info("Discovered %s", pformat(device_info))
    device_name = f"{device_info.manufacturer}-{device_info.serial_number}"

    update_dell_drac_settings(bmc)

    bmc_set_hostname(bmc, device_info.bmc_hostname, device_name)

    node = ironic_node.create_or_update(
        bmc=bmc,
        name=device_name,
        manufacturer=device_info.manufacturer,
    )
    logger.info("%s complete for %s", __file__, bmc.ip_address)

    return node.uuid


def argument_parser():
    """Parse runtime arguments."""
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__), description="Ingest Baremetal Node"
    )
    parser.add_argument("--bmc-ip-address", type=str, required=True, help="BMC IP")
    parser.add_argument(
        "--old-bmc-password", type=str, required=False, help="Old Password"
    )
    return parser


if __name__ == "__main__":
    main()
