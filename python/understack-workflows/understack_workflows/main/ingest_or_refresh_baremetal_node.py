import json
import sys

from understack_workflows.helpers import setup_logger
from understack_workflows.helpers import credential

import understack_workflows.bmc_sync_creds
import understack_workflows.bmc_update_bios_settings
import understack_workflows.ironic_node_action

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
       - what did prashant just do?

    -  Find or create this server in Nautobot

       locate server by serial number.  Ensure correct:
       - interfaces, including BMC
       - interface mac addresses
       - BMC interface IP addresses
       - device type?  What else?

    -  Find or create this baremetal node in Ironic
       - create ports with MACs
       - advance to available state
       - set flavor?  what else?

    """

    device_id, device_hostname, interface_name, bmc = event_payload(get_args())
    logger.info(f"{__file__} starting for {bmc.ip_address} {device_id=}")

    bmc_sync_creds.sync_creds(bmc.ip_address, bmc.password, logger)

    bmc_update_bios_settings.update_dell_bios(bmc, logger)

    # well, it already exists in nautobot
    # create_in_nautobot()

    _ironic_provision_state = ironic_node_action.create_or_update(device_id, bmc, logger)

    device_info = redfish_device_discovery.device_info(bmc)

    sync_interfaces.from_nautobot_to_ironic(device_id)


    logger.info(f"{__file__} complete successfully for {bmc.ip_address}")

def get_args() -> dict:
    if len(sys.argv) < 1:
        raise ValueError(
            "Please provide node configuration in JSON format as first argument."
        )
    return json.loads(sys.argv[1])

def event_payload(payload) -> (str, str, Bmc):
    """Parse Nautobot webhook event data

    Here we consume the event that Nautobot publishes whenever an ethernet
    interface is updated.  (Other types of event will raise an error)

    returns (device_uuid: str, hostname: str, bmc: Bmc)
    """
    logger.debug(f"Received Event: {json.dumps(payload, indent=2)}")

    data = payload.get("data")
    model = payload.get("model")

    if model not in ["interface"]:
        raise ValueError(f"'{model}' events not supported")

    device_uuid = data["device"]["id"]
    device_hostname = data["device"]["name"]
    interface_name = data["name"]
    bmc_ip_address = data['ip_addresses'][0]['host']

    the_bmc = bmc(bmc_ip_address, bmc_type = interface_name)

    return device_uuid, device_hostname, the_bmc


def bmc(ip_address, bmc_type) -> Bmc:
    bmc_master_key = credential("bmc_master", "key")
    password = standard_password(self.ip_address, bmc_master_key)
    return Bmc(bmc_type=bmc_type, ip_address=ip_address, password=password)
