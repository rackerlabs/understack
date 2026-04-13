# pylint: disable=E1131,C0103

import argparse
import logging
import os
import time

from ironicclient.v1.node import Node

from understack_workflows import ironic_node
from understack_workflows.bmc import Bmc
from understack_workflows.bmc import RedfishRequestError
from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.bmc_bios import update_dell_bios_settings
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import chassis_info
from understack_workflows.bmc_credentials import set_bmc_password
from understack_workflows.bmc_hostname import bmc_set_hostname
from understack_workflows.bmc_settings import update_dell_drac_settings
from understack_workflows.helpers import setup_logger
from understack_workflows.pxe_port_heuristic import guess_pxe_interfaces

logger = logging.getLogger(__name__)

POST_POWER_ON_WAIT_SECONDS = 120
POST_POWER_ON_RETRY_SECONDS = 30
POST_POWER_ON_MAX_RETRIES = 8


def main() -> None:
    """On-board new or Refresh existing baremetal node.

    - connect to the BMC using standard password, if that fails then use
      password supplied in --old-bmc-password option, or factory default

    - ensure standard BMC password is set, and other basic BMC settings

    -  from BMC, discover basic hardware info:
       - manufacturer, model number, serial number
       - CPU model(s), RAM size and local storage
       - list ethernet interfaces with:
          - name like BMC or SLOT.NIC.1-1
          - MAC address
          - LLDP connections [{remote_mac, remote_interface_name}]

    - Figure out which NICs to enable for PXE

    - Configure our standard BIOS settings including HTTP boot devices

    - Find or create this baremetal node in Ironic
      - Set the name to "{manufacturer}-{servicetag}"
      - Set the driver as appropriate for the manufacturer/model
      - Configure RAID
      - Transition through enrol->manage->inspect->cleaning->provide
    """
    setup_logger()
    args = argument_parser().parse_args()

    enrol(
        ip_address=args.ip_address,
        old_password=args.old_password,
        firmware_update=args.firmware_update,
        pxe_switch_macs=parse_maclist(str(args.pxe_switch_macs)),
        raid_configure=args.raid_configure,
        external_cmdb_id=args.external_cmdb_id,
    )


def parse_maclist(maclist: str) -> set[str]:
    return {mac.strip().upper() for mac in maclist.split(",")}


def enrol(
    ip_address: str,
    firmware_update: bool,
    raid_configure: bool,
    pxe_switch_macs: set[str],
    old_password: str | None,
    external_cmdb_id: str | None = None,
) -> None:
    logger.info("Starting enrol workflow for bmc_ip_address=%s", ip_address)
    logger.info("  pxe_switch_macs=%s", pxe_switch_macs)

    if external_cmdb_id:
        logger.info("  external_cmdb_id=%s", external_cmdb_id)

    bmc = bmc_for_ip_address(ip_address)
    device_info = initialize_bmc(bmc, old_password)

    if insufficient_lldp_data(device_info):
        device_info = power_on_and_wait(bmc, device_info)

    pxe_interfaces = guess_pxe_interfaces(device_info, pxe_switch_macs)
    logger.info("Selected %s as PXE interfaces", pxe_interfaces)

    node = ironic_node.create_or_update(
        bmc=bmc,
        name=device_name(device_info),
        manufacturer=device_info.manufacturer,
        external_cmdb_id=external_cmdb_id,
        enrolled_pxe_ports=pxe_interfaces,
    )

    # Once we've added to the node to Ironic, perform a redfish
    # inspection immediately to populate the BIOS data and initial
    # hardware information
    ironic_node.inspect_out_of_band(node)

    if raid_configure:
        # Raid configuration runs a clean step which does a PXE boot.  That
        # can't work unless we first apply_bios_settings.
        # TODO: why isn't skip_ramdisk working here?
        apply_bios_settings(bmc, pxe_interfaces)
        configure_raid(node, bmc)
    else:
        logger.info("%s RAID configuration was not requested", node.uuid)

    ironic_node.inspect_out_of_band(node)

    # Anecdotally, applying firmware updates can upset the next-boot HTTP, and
    # potentially even upset the bios-settings configuration job in the iDRAC,
    # so we do firmware first, which causes a reboot, and only then do we set
    # the BIOS settings.
    #
    # Also, just maybe, the bios setting keys we are trying to set might not be
    # available in the old version of the bios, in which case we need to boot
    # the bios before redfish will allow us to set those settings.
    if firmware_update:
        ironic_node.apply_firmware_updates(node)

    # Applying BIOS settings on Dell servers requires a reboot which we achieve
    # by initiating agent inspection.  Agent inspection requires BIOS settings
    # (to set boot device).  Therefore these two actions must go hand-in-hand.
    #
    # Note that we may have already applied BIOS settings above.  That is okay,
    # it is idempotent.
    apply_bios_settings(bmc, pxe_interfaces)
    ironic_node.inspect(node)

    # After successful inspection, our node is left in "manageable" state.  All
    # being well, the "provide" action will transition manageable -> cleaning ->
    # available.
    ironic_node.transition(node, target_state="provide", expected_state="available")
    logger.info("Completed enrol workflow for bmc_ip_address=%s", ip_address)


def initialize_bmc(bmc: Bmc, old_password: str | None) -> ChassisInfo:
    """Discover and configure BMC with Undercloud standard settings."""
    set_bmc_password(
        ip_address=bmc.ip_address,
        new_password=bmc.password,
        old_password=old_password,
    )

    device_info = chassis_info(bmc)
    for line in device_info.dump:
        logger.info("Discovered %s", line)

    if device_info.manufacturer == "Dell":
        update_dell_drac_settings(bmc)

    bmc_set_hostname(bmc, device_info.bmc_hostname, device_name(device_info))
    return device_info


def insufficient_lldp_data(device_info: ChassisInfo) -> bool:
    """Whether the device_info is populated with switch connections.

    We normally get LLDP data for the BMC's own (out of band) interface but that
    is not relevant to our investigation so we exclude known BMC interface
    names.

    If the server has been powered on, we will often get LLDP data for the other
    ports as well.
    """
    for i in device_info.interfaces:
        if (
            "DRAC" not in i.name.upper()
            and "ILO" not in i.name.upper()
            and i.remote_switch_mac_address
        ):
            return False

    return True


def power_on_and_wait(bmc: Bmc, device_info: ChassisInfo) -> ChassisInfo:
    """If power is off, switch on and wait a minute."""
    if device_info.power_on:
        logger.debug("Power is on")
        return device_info

    logger.info("Power is off. Switching on and waiting for links to stabilize")
    # TODO: figure out how to do this with sushy
    bmc.redfish_request(
        path=f"{bmc.get_system_path()}/Actions/ComputerSystem.Reset",
        payload={"ResetType": "On"},
        method="POST",
    )
    time.sleep(POST_POWER_ON_WAIT_SECONDS)

    for attempt in range(POST_POWER_ON_MAX_RETRIES + 1):
        try:
            return chassis_info(bmc)
        except RedfishRequestError as exc:
            if not _is_temporary_redfish_unavailable(exc):
                raise
            if attempt == POST_POWER_ON_MAX_RETRIES:
                raise
            logger.warning(
                "BMC Redfish data is temporarily unavailable after power on for %s. "
                "Retrying in %s seconds.",
                bmc.ip_address,
                POST_POWER_ON_RETRY_SECONDS,
            )
            time.sleep(POST_POWER_ON_RETRY_SECONDS)

    raise AssertionError("unreachable")


def _is_temporary_redfish_unavailable(exc: RedfishRequestError) -> bool:
    message = str(exc)
    return "HTTP 503" in message or "ServiceTemporarilyUnavailable" in message


def device_name(device_info: ChassisInfo) -> str:
    return f"{device_info.manufacturer}-{device_info.serial_number}"


def configure_raid(node: Node, bmc: Bmc):
    raid_details = discover_controller_details(bmc)
    if not raid_details:
        logger.info("%s No RAID hardware found in node", node.uuid)
        return

    logger.info("%s Applying RAID configuration", node.uuid)
    raid_config = build_raid_config(**raid_details)
    ironic_node.set_target_raid_config(node, raid_config)
    ironic_node.transition(
        node,
        target_state="clean",
        expected_state="manageable",
        clean_steps=[
            {"interface": "raid", "step": "delete_configuration"},
            {"interface": "raid", "step": "create_configuration"},
        ],
        disable_ramdisk=True,
    )


def discover_controller_details(bmc: Bmc) -> dict | None:
    """Parse available RAID controller details for execution."""
    system_objects = bmc.sushy().get_system_collection().get_members()
    system = system_objects[0]
    for controller in system.storage.get_members():
        if "RAID" in controller.identity:
            return {
                "controller": controller.identity,
                "physical_disks": [d.identity for d in controller.drives],
            }
    return None


def build_raid_config(controller: str, physical_disks: list[str]):
    """Return a raid config supported by ironic for cleanup tasks."""
    if len(physical_disks) < 2:
        raid_level = "0"
    elif len(physical_disks) > 2:
        raid_level = "5"
    else:
        raid_level = "1"

    result = {
        "logical_disks": [
            {
                "controller": controller,
                "is_root_volume": True,
                "physical_disks": physical_disks,
                "raid_level": raid_level,
                "size_gb": "MAX",
            }
        ]
    }
    return result


def apply_bios_settings(bmc: Bmc, pxe_interfaces: list[str]):
    update_dell_bios_settings(bmc, pxe_interfaces=pxe_interfaces)


def parse_bool(value: str) -> bool:
    return value.lower() == "true"


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Run the server enrol workflow",
    )
    parser.add_argument("--ip-address", required=True, help="IP Address of BMC")
    parser.add_argument(
        "--old-password",
        required=False,
        help="Old (current) BMC password",
    )
    parser.add_argument(
        "--firmware-update",
        type=parse_bool,
        default=False,
        help="Run firmware update runbooks after inspection",
    )
    parser.add_argument(
        "--raid-configure",
        type=parse_bool,
        default=True,
        help="Configure RAID before inspection",
    )
    parser.add_argument(
        "--external-cmdb-id",
        required=False,
        default="",
        help="External CMDB ID for RXDB integration",
    )
    parser.add_argument(
        "--pxe-switch-macs",
        required=False,
        default="",
        help="Chassis MAC address of switches providing PXE network",
    )
    return parser


if __name__ == "__main__":
    main()
