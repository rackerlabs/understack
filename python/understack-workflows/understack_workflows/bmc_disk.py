import math
from dataclasses import dataclass

from understack_workflows.bmc import Bmc
from understack_workflows.bmc import RedfishRequestError
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


@dataclass(frozen=True)
class Disk:
    """Disk Data Class."""

    media_type: str
    model: str
    name: str
    health: str
    capacity_bytes: int

    def __repr__(self) -> str:
        """Returns disk name."""
        return self.name

    @property
    def capacity_gb(self) -> int:
        """Capacity Math."""
        return math.ceil(self.capacity_bytes / 10**9)

    @staticmethod
    def from_path(bmc: Bmc, path: str):
        """Disk path request."""
        disk_data = bmc.redfish_request(path)

        return Disk(
            media_type=disk_data["MediaType"],
            model=disk_data["Model"],
            name=disk_data["Name"],
            health=disk_data.get("Status", {}).get("Health", "Unknown"),
            capacity_bytes=disk_data["CapacityBytes"],
        )


def physical_disks(bmc: Bmc) -> list[Disk]:
    """Retrieve list of physical physical_disks."""
    try:
        storage_member_paths = [
            member["@odata.id"]
            for member in bmc.redfish_request(bmc.system_path + "/Storage")["Members"]
        ]
        disks = [
            bmc.redfish_request(drive_path)["Drives"]
            for drive_path in storage_member_paths
        ]
        disk_paths = [disk for sublist in disks for disk in sublist]
        disk_list = [Disk.from_path(bmc, path=disk["@odata.id"]) for disk in disk_paths]
        logger.debug("Retrieved %d disks.", len(disk_list))
        return disk_list
    except RedfishRequestError as err:
        logger.error("Failed retrieving disk info: %s", err)
        raise (err) from err


def smallest_disk_size(bmc: Bmc) -> int:
    """Returns size of a smallest disk in a given machine (in Gigabytes)."""
    return min(physical_disks(bmc), key=lambda x: x.capacity_gb).capacity_gb
