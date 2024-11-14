import math
from dataclasses import dataclass

from understack_workflows.bmc import Bmc
from understack_workflows.bmc import RedfishError
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


REDFISH_DISKS_PATH = "/redfish/v1/Systems/System.Embedded.1/Storage/RAID.SL.1-1"


@dataclass(frozen=True)
class Disk:
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
        return math.ceil(self.capacity_bytes / 10**9)

    @staticmethod
    def from_path(bmc: Bmc, path: str):
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
        disks = bmc.redfish_request(REDFISH_DISKS_PATH)["Drives"]
        disk_list = [Disk.from_path(bmc, path=disk["@odata.id"]) for disk in disks]
        logger.debug("Retrieved %d disks.", len(disk_list))
        return disk_list
    except RedfishError as err:
        logger.error("Failed retrieving disk info from %s: %s", REDFISH_DISKS_PATH, err)
        raise (err) from err


def smallest_disk_size(bmc: Bmc) -> int:
    """Returns size of a smallest disk in a given machine (in Gigabytes)."""
    return min(physical_disks(bmc), key=lambda x: x.capacity_gb).capacity_gb
