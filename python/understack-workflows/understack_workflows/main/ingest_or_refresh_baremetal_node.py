import json
import sys

from understack_workflows.helpers import setup_logger
from understack_workflows.bmc_credentials import set_bmc_password
from understack_workflows.bmc_bios import update_dell_bios_settings
from understack_workflows.nautobot_event_parser import parse_event
from understack_workflows.bmc import bmc_for_ip_address
import understack_workflows.ironic_node

logger = setup_logger(__name__)

def main():
    """On-board new or Refresh existing baremetal node

    We have been invoked because a baremetal node was detected.

    - connect to the BMC and ensure standard password is set

    - TODO: SSL certificate

    - TODO: update BMC firmware

    - TODO: set NTP Server IPs for DRAC (IP addresses different per region)

    -  Using BMC, configure our standard BIOS settings

       - set PXE boot device
       - set timezone to UTC

    -  from BMC, discover basic hardware info:

       - serial number, etc
       - enumerate ethernet interfaces with MACs
       - what else did prashant just do?
       - can we get LLDP connections?

    -  Find or create this server in Nautobot

       locate server by serial number.  Ensure correct:
       - interfaces, including BMC
       - interface mac addresses
       - BMC interface IP addresses
       - device type?  What else?
       - if we have LLDP info, connect up switchports.  Error if switches don't exist

    -  Find or create this baremetal node in Ironic
       - create ports with MACs
       - advance to available state
       - set flavor?  what else?

    """

    device_id, device_hostname, bmc_ip_address, bmc_type = parse_event(get_args())

    logger.info(f"{__file__} starting for {device_id=} {device_hostname=}")
    logger.info(f"Parsed event: {bmc_type=} {bmc_ip_address=}")

    bmc = bmc_for_ip_address(bmc_ip_address, bmc_type)

    set_bmc_password(bmc.ip_address, bmc.password)

    update_dell_bios_settings(bmc, logger)

    device_info = redfish_device_discovery.device_info(bmc)

    # well, it already exists in nautobot
    # create_in_nautobot()

    _ironic_provision_state = ironic_node.create_or_update(device_id, bmc, logger)

    sync_interfaces.from_nautobot_to_ironic(device_id)


    logger.info(f"{__file__} complete successfully for {bmc.ip_address}")

def get_args() -> dict:
    if len(sys.argv) < 1:
        raise ValueError(
            "Please provide event in JSON format as first argument"
        )
    return json.loads(sys.argv[1])

