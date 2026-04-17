# pylint: disable=E1131,C0103

import argparse
import logging
import os

from ironicclient.v1.node import Node

from understack_workflows import ironic_node
from understack_workflows.bmc import Bmc
from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.bmc_bios import update_dell_bios_settings
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import chassis_info
from understack_workflows.bmc_credentials import set_bmc_password
from understack_workflows.bmc_hostname import bmc_set_hostname
from understack_workflows.bmc_settings import update_dell_drac_settings
from understack_workflows.helpers import setup_logger

logger = logging.getLogger(__name__)

MAX_PXE_INTERFACES = 8


def main() -> None:
    """On-board a new baremetal node, or refresh an existing one.

    - Connect to the BMC using standard password, if that fails then use the
      password supplied in --old-bmc-password option, or factory default.

    - Ensure standard BMC password is set, and other basic BMC settings.

    - From BMC, discover basic chassis info: manufacturer, model, serial.

    - Find or create this baremetal node in Ironic:
      - Set the name to "{manufacturer}-{servicetag}".
      - Set the driver as appropriate for the manufacturer/model.
      - Set the node's external_cmdb_id, if one was provided.

    - Perform agent inspection via virtual-media boot to capture the full
      hardware inventory and LLDP-confirmed switch topology.

      Using virtual-media avoids having to configure PXE during the initial
      phase, however the IPA agent still requires DHCP autoconfiguration, so it
      needs to be connected to the provisioning VLAN, and it needs at least one
      port in Neutron to be configured for "enrol".

    - Configure the Dell HTTP-boot BIOS entries using the LLDP-confirmed PXE
      interfaces, then flip the node back to its final production http-ipxe boot
      mode for cleaning and provisioning (we prefer PXE-based booting over
      virtual media, for performance reasons).

    - Optionally configure RAID.

    - Optionally apply firmware updates.

    - Transition the node to the 'available' state (implies cleaning).
    """
    setup_logger()
    args = argument_parser().parse_args()

    enrol(
        ip_address=args.ip_address,
        old_password=args.old_password,
        firmware_update=args.firmware_update,
        raid_configure=args.raid_configure,
        external_cmdb_id=args.external_cmdb_id,
    )


def enrol(
    ip_address: str,
    firmware_update: bool,
    raid_configure: bool,
    old_password: str | None,
    external_cmdb_id: str | None = None,
) -> None:
    logger.info("Starting enrol workflow for bmc_ip_address=%s", ip_address)

    if external_cmdb_id:
        logger.info("  external_cmdb_id=%s", external_cmdb_id)

    bmc = bmc_for_ip_address(ip_address)
    device_info = initialize_bmc(bmc, old_password)

    node = ironic_node.create_or_update(
        bmc=bmc,
        name=device_name(device_info),
        manufacturer=device_info.manufacturer,
        external_cmdb_id=external_cmdb_id,
    )

    # Out-of-band redfish inspection populates data including baremetal ports.
    #
    # Our hooks augment the ironic baremetal port with the BMC-reported
    # interface name (e.g. NIC.Integrated.1-1) as well as some placeholder
    # "enrol" dummy data that is required by Ironic/Neutron to perform agent
    # inspection.  Neutron needs to assign a port to the provisioning network
    # and it bails out unless we have ports with pxe_enabled, local_link_info,
    # etc.
    ironic_node.inspect_out_of_band(node)

    # Agent inspection via virtual media gathers LLDP and full hardware
    # inventory.
    inspect_via_virtual_media(node)

    pxe_interface = ironic_node.pxe_enabled_bios_name(node)
    if not pxe_interface:
        raise RuntimeError(
            f"[node:{node.uuid}] Agent inspection produced no pxe_enabled ports "
            "cannot configure HTTP boot."
        )
    logger.info("[node:%s] Selected PXE interface %s", node.uuid, pxe_interface)

    update_dell_bios_settings(bmc, pxe_interface=pxe_interface)

    if raid_configure:
        configure_raid(node, bmc)
        # RAID reconfiguration changes the disk layout; refresh inventory.
        ironic_node.inspect_out_of_band(node)
    else:
        logger.info("%s RAID configuration was not requested", node.uuid)

    if firmware_update:
        ironic_node.apply_firmware_updates(node)

    ironic_node.transition(node, target_state="provide", expected_state="available")
    logger.info("Completed enrol workflow for bmc_ip_address=%s", ip_address)


def inspect_via_virtual_media(node: Node) -> None:
    """Run agent inspection booted via virtual media.

    The node is temporarily flipped to a virtual-media boot_interface so the
    agent ramdisk boots from a BMC-attached ISO rather than via PXE.  After
    inspection the boot_interface is reset to the steady-state value used for
    cleaning and provisioning.
    """
    refreshed = ironic_node.refresh(node, fields=["driver"])
    vm_boot = ironic_node.virtual_media_boot_interface_for(refreshed.driver)

    logger.info(
        "[node:%s] Switching boot_interface to %s for agent inspection",
        node.uuid,
        vm_boot,
    )
    ironic_node.patch(node, [f"boot_interface={vm_boot}"])
    try:
        ironic_node.inspect(node)
    finally:
        ironic_node.patch(
            node, [f"boot_interface={ironic_node.STEADY_STATE_BOOT_INTERFACE}"]
        )


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
    return parser


if __name__ == "__main__":
    main()
