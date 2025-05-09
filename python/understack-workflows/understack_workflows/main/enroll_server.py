import argparse
import os
from pprint import pformat

import pynautobot

from understack_workflows import ironic_node
from understack_workflows import nautobot_device
from understack_workflows import sync_interfaces
from understack_workflows import topology
from understack_workflows.bmc import Bmc
from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.bmc_bios import update_dell_bios_settings
from understack_workflows.bmc_credentials import set_bmc_password
from understack_workflows.bmc_hostname import bmc_set_hostname
from understack_workflows.bmc_network_config import bmc_set_permanent_ip_addr
from understack_workflows.bmc_settings import update_dell_drac_settings
from understack_workflows.discover import discover_chassis_info
from understack_workflows.flavor_detect import guess_machine_flavor
from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.nautobot_device import NautobotDevice

logger = setup_logger(__name__)


def main():
    """On-board new or Refresh existing baremetal node.

    We have been invoked because a baremetal node is available.

    Pre-requisites in Nautobot:

    All connected switches must have a device with the base MAC address stored
    in the asset tag field.

    The Rack and Location of the switches must be correct (they will be copied
    verbatim to the newly created server Device).

    The server Device type must exist, with a name that matches the "model" as
    reported by the BMC.

    The DRAC IP Prefix must exist.

    This script has the following order of operations:

    - connect to the BMC using standard password, if that fails then use
      password supplied in --old-bmc-password option, or factory default

    - ensure standard BMC password is set

    - if DHCP, set permanent IP address, netmask, default gw

    - if server is off, power it on and wait (otherwise LLDP doesn't work)

    - TODO: create and install SSL certificate

    - TODO: set NTP Server IPs for DRAC
      (NTP server IP addresses are different per region)

    -  Using BMC, configure our standard BIOS settings
       - set PXE boot device
       - set timezone to UTC

    -  from BMC, discover basic hardware info:
       - manufacturer, model number, serial number
       - CPU model(s), RAM size and local storage
       - list ethernet interfaces with:
          - name like BMC or SLOT.NIC.1-1
          - MAC address
          - LLDP connections [{remote_mac, remote_interface_name}]

    - Find or create this server in Nautobot by serial number.

    - set name, manufacturer, model, serial, location, rack

    - Find BMC interface

    - For each server interface
        - find or create server interface by name in nautobot
        - set interface mac addresses
        - look up switch by mac addr (is stored in Nautobot's asset tag field)
        - look up switch interface by name
        - find or create cable

    - create BMC IP address assignment for BMC interface - convert our type
      "dhcp" IP Address to type "host" and associate it with the interface

    - Determine flavor of the server based on the information collected from BMC
    - Find or create this baremetal node in Ironic
       - create ports with MACs (omit BMC port) and set one to PXE
       - TODO advance to available state
       - set flavor

    """
    args = argument_parser().parse_args()

    bmc_ip_address = args.bmc_ip_address
    logger.info("%s starting for bmc_ip_address=%s", __file__, bmc_ip_address)

    url = args.nautobot_url
    token = args.nautobot_token or credential("nb-token", "token")
    nautobot = pynautobot.api(url, token=token)

    bmc = bmc_for_ip_address(bmc_ip_address)

    nb_device = enroll_server(bmc, nautobot, args.old_bmc_password)

    # argo workflows captures stdout as the results which we can use
    # to return the device UUID
    print(str(nb_device.id))


def enroll_server(bmc: Bmc, nautobot, old_password: str | None) -> NautobotDevice:
    set_bmc_password(
        ip_address=bmc.ip_address,
        new_password=bmc.password,
        old_password=old_password,
    )

    device_info = discover_chassis_info(bmc)
    logger.info("Discovered %s", pformat(device_info))

    update_dell_drac_settings(bmc)

    nb_device = nautobot_device.find_or_create(device_info, nautobot)
    pxe_interface = topology.pxe_interface_name(nb_device)

    bmc_set_hostname(bmc, device_info.bmc_hostname, nb_device.name)

    # Be sure to only do this after Nautobot IPAddress has been changed from
    # DHCP, otherwise our IP might be handed out to someone else.
    bmc_set_permanent_ip_addr(bmc, device_info.bmc_interface)

    # Note the above may require a restart of the DRAC, which in turn may delete
    # any pending BIOS jobs, so do BIOS settings after the DRAC settings.
    update_dell_bios_settings(bmc, pxe_interface=pxe_interface)

    flavor = guess_machine_flavor(device_info, bmc)
    resource_class = f"baremetal.{flavor}"

    _ironic_provision_state = ironic_node.create_or_update(
        ironic_node.NodeMetadata(
            uuid=nb_device.id,
            hostname=nb_device.name,
            manufacturer=device_info.manufacturer,
            resource_class=resource_class,
        ),
        bmc,
    )
    logger.info("%s _ironic_provision_state=%s", nb_device.id, _ironic_provision_state)

    sync_interfaces.from_nautobot_to_ironic(nb_device, pxe_interface=pxe_interface)

    logger.info("%s complete for %s", __file__, bmc.ip_address)

    return nb_device


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__), description="Ingest Baremetal Node"
    )
    parser.add_argument("--bmc-ip-address", type=str, required=True, help="BMC IP")
    parser.add_argument(
        "--old-bmc-password", type=str, required=False, help="Old Password"
    )
    parser = parser_nautobot_args(parser)
    return parser


if __name__ == "__main__":
    main()
