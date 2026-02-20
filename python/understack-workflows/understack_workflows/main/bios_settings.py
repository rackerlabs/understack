import argparse
import logging
import os

from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.bmc_bios import update_dell_bios_settings
from understack_workflows.bmc_chassis_info import chassis_info
from understack_workflows.helpers import setup_logger
from understack_workflows.pxe_port_heuristic import guess_pxe_interface

logger = setup_logger(__name__)

# These are extremely verbose by default:
for name in ["ironicclient", "keystoneauth", "stevedore"]:
    logging.getLogger(name).setLevel(logging.INFO)


def main():
    """Update BIOS settings to undercloud standard for the given server.

    - Using BMC, configure our standard BIOS settings
       - set PXE boot device
       - set timezone to UTC
       - set the hostname

    NOTE: take care with order of execution of these workflow steps:

    When asked to change BIOS settings, iDRAC enqueues a "job" that will execute
    on next boot of the server.

    The assumption for this workflow is that this server will shortly be PXE
    booting into the IPA image for cleaning or inspection.

    Therefore this workflow does not itself boot the server.

    Any subsequent iDRAC operations such as a code update or ironic validation
    can clear our pending BIOS update job from the iDRAC job queue.  Before we
    perform any such operation, we should first do something that will cause a
    reboot of the server.
    """
    args = argument_parser().parse_args()

    bmc_ip_address = args.bmc_ip_address
    logger.info("%s starting for bmc_ip_address=%s", __file__, bmc_ip_address)

    bmc = bmc_for_ip_address(bmc_ip_address)
    device_info = chassis_info(bmc)
    pxe_interface = guess_pxe_interface(device_info)
    logger.info("Selected %s as PXE interface", pxe_interface)

    update_dell_bios_settings(bmc, pxe_interface=pxe_interface)


def argument_parser():
    """Parse runtime arguments."""
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__), description="Update BIOS Settings"
    )
    parser.add_argument("--bmc-ip-address", type=str, required=True, help="BMC IP")
    return parser


if __name__ == "__main__":
    main()
