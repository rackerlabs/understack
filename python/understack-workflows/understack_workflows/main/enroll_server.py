import argparse
import logging
import os
from pprint import pformat


from understack_workflows import ironic_node
from understack_workflows.sync_interfaces import update_ironic_baremetal_ports
from understack_workflows import topology
from understack_workflows.bmc import Bmc
from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.bmc_bios import update_dell_bios_settings
from understack_workflows.bmc_credentials import set_bmc_password
from understack_workflows.bmc_hostname import bmc_set_hostname
from understack_workflows.bmc_settings import update_dell_drac_settings
from understack_workflows.discover import discover_chassis_info
from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

# These are extremely verbose by default:
for name in ["ironicclient", "keystoneauth", "stevedore"]:
    logging.getLogger(name).setLevel(logging.INFO)


def main():
    """On-board new or Refresh existing baremetal node.

    We have been invoked because a baremetal node is available.

    Pre-requisites:

    All connected switches must be known to us via the base MAC address in our
    data center yaml data.

    The server Device type must exist, with a name that matches the "model" as
    reported by the BMC.

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

    - Determine flavor of the server based on the information collected from BMC

    - Find or create this baremetal node in Ironic
       - create baremetal ports for each NIC except BMC. Set one of them to PXE.
       - set flavor
    """
    args = argument_parser().parse_args()

    bmc_ip_address = args.bmc_ip_address
    logger.info("%s starting for bmc_ip_address=%s", __file__, bmc_ip_address)

    bmc = bmc_for_ip_address(bmc_ip_address)

    device_id = enroll_server(bmc, args.old_bmc_password)

    # argo workflows captures stdout as the results which we can use
    # to return the device UUID
    print(device_id)


def enroll_server(bmc: Bmc, old_password: str | None) -> str:
    set_bmc_password(
        ip_address=bmc.ip_address,
        new_password=bmc.password,
        old_password=old_password,
    )

    device_info = discover_chassis_info(bmc)
    logger.info("Discovered %s", pformat(device_info))

    device_name = f"{device_info.manufacturer}-{device_info.serial_number}"

    update_dell_drac_settings(bmc)

    pxe_interface = topology.pxe_interface_name(device_info.interfaces)

    bmc_set_hostname(bmc, device_info.bmc_hostname, device_name)

    # Note the above may require a restart of the DRAC, which in turn may delete
    # any pending BIOS jobs, so do BIOS settings after the DRAC settings.
    update_dell_bios_settings(bmc, pxe_interface=pxe_interface)

    node = ironic_node.create_or_update(
        bmc=bmc,
        name=device_name,
        manufacturer=device_info.manufacturer,
    )
    logger.info("%s _ironic_provision_state=%s", device_name, node.provision_state)

    update_ironic_baremetal_ports(
        ironic_node=node,
        discovered_interfaces=device_info.interfaces,
        pxe_interface_name=pxe_interface,
    )

    logger.info("%s complete for %s", __file__, bmc.ip_address)

    return node.uuid


def argument_parser():
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
