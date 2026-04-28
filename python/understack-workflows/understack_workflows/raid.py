import logging
from collections.abc import Iterable
from dataclasses import dataclass

from ironicclient.v1.node import Node

from understack_workflows import ironic_node

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PhysicalDisk:
    id: str
    controller: str
    size_gb: int


def configure_raid(node: Node, inventory: dict):
    """Set target RAID config && run clean steps to re-create the RAID array.

    We find any storage controllers that have "RAID" in the name and have one or
    more disks attached.

    We group disks by size (creating an array of mismatched disks wastes space
    and/or performance).

    We form a logical volume from each group of disks on each controller.

    The volume that has the smallest disks is marked as the "root volume".
    """
    physical_disks = _physical_disks_from_inventory(inventory)
    if not physical_disks:
        logger.info("%s No RAID hardware found in node", node.uuid)
        return

    raid_config = _generate_raid_config(physical_disks)
    logger.info("%s Applying RAID configuration", node.uuid)
    ironic_node.set_target_raid_config(node, raid_config)

    ironic_node.transition(
        node,
        target_state="clean",
        expected_state="manageable",
        clean_steps=[
            {"interface": "raid", "step": "delete_configuration"},
            {"interface": "raid", "step": "create_configuration"},
        ],
        disable_ramdisk=False,
    )


def _generate_raid_config(physical_disks: set[PhysicalDisk]) -> dict:
    """Return a raid config supported by Ironic's clean steps."""
    return {"logical_disks": list(_logical_disks(physical_disks))}


def _logical_disks(disks: set[PhysicalDisk]):
    is_root_volume = True
    for metadata, diskgroup in sorted(_group_by_size_and_controller(disks).items()):
        (_, controller_id) = metadata
        yield {
            "controller": controller_id,
            "physical_disks": sorted(disk.id for disk in diskgroup),
            "raid_level": _raid_level(len(diskgroup)),
            "size_gb": "MAX",
            "is_root_volume": is_root_volume,
        }
        is_root_volume = False


def _physical_disks_from_inventory(inventory: dict) -> set[PhysicalDisk]:
    """Parse Inventory data as returned by the redfish inspection.

    Answer the set of PhysicalDisks that are associated with RAID controllers in
    this server.
    """
    inventory_data = inventory.get("inventory", {})
    return {
        disk
        for controller in inventory_data.get("storage_controllers", [])
        for disk in _physical_disks_for_controller(controller)
    }


def _physical_disks_for_controller(storage_controller: dict) -> set[PhysicalDisk]:
    controller_id = str(storage_controller.get("id"))
    disks = storage_controller.get("drives", [])

    if "RAID" not in controller_id.upper():
        return set()

    return {
        PhysicalDisk(
            id=disk["id"],
            controller=controller_id,
            size_gb=disk["size"] // 10**9,
        )
        for disk in disks
    }


def _group_by_size_and_controller(
    disks: Iterable[PhysicalDisk],
) -> dict[tuple, list[PhysicalDisk]]:
    disks_by_size_and_controller = {}
    for disk in disks:
        key = (disk.size_gb, disk.controller)
        disks_by_size_and_controller.setdefault(key, []).append(disk)
    return disks_by_size_and_controller


def _raid_level(disk_count: int) -> str:
    match disk_count:
        case 1:
            return "0"
        case 2:
            return "1"
        case _:
            return "5"
