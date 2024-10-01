import json
import sys

from understack_workflows.helpers import setup_logger
from understack_workflows.bmc_credentials import set_bmc_password
from understack_workflows.bmc_bios import update_dell_bios_settings
from understack_workflows.bmc import bmc_for_ip_address
import understack_workflows.ironic_node
from understack_workflows import bmc_chassis_info
from understack_workflows import nautobot_device

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
       - manufacturer, model number, serial number
       - list ethernet interfaces with:
          - name like BMC or SLOT.NIC.1-1
          - MAC address
          - LLDP connections [{remote_mac, remote_interface_name}]

    - Find or create this server in Nautobot
        - locate server by serial number.
        - set manufacturer, model number, serial number
        - Find or create BMC interface with IP address

    - For each server interface
        - find or create server interface by name in nautobot
        - set interface mac addresses
        - look up remote mac in nautobot
        - add interface to switch if missing
        - make cable

    -  Find or create this baremetal node in Ironic
       - create ports with MACs
       - advance to available state
       - set flavor?  what else?

    """

    bmc_ip_address, bmc_mac = get_args()
    logger.info(f"{__file__} starting for {bmc_ip_address=}")

    url = "https://nautobot.dev.undercloud.rackspace.net/"
    token = credential("nb-token", "token")
    nautobot = pynautobot.api(url, token=token)

    bmc = bmc_for_ip_address(bmc_ip_address, bmc_type)
    set_bmc_password(bmc.ip_address, bmc.password)
    update_dell_bios_settings(bmc, logger)

    device_info = chassis_info(bmc)
    device_uuid = nautobot_device.find_or_create(device_info, nautobot)

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

def get_args() -> str:
    if len(sys.argv) < 1:
        raise ValueError(
            "Please provide BMC IP Address as first argument"
        )
    return sys.argv[1], sys.argv[2]
