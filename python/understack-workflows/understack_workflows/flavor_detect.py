import os

from flavor_matcher.machine import Machine
from flavor_matcher.matcher import FlavorSpec
from flavor_matcher.matcher import Matcher

from understack_workflows import bmc_disk
from understack_workflows.bmc import Bmc
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)
FLAVORS_DIR = os.getenv("FLAVORS_DIR", "/etc/understack_flavors/")
FLAVORS = FlavorSpec.from_directory(FLAVORS_DIR)
logger.info(f"Loaded {len(FLAVORS)} flavor specifications.")


def guess_machine_flavor(device_info: ChassisInfo, bmc: Bmc) -> str:
    memory_mb = (device_info.memory_gib * 1024**3) // 10**6

    machine = Machine(
        memory_mb=memory_mb,
        cpu=device_info.cpu,
        disk_gb=bmc_disk.smallest_disk_size(bmc),
        model=device_info.model_number,
    )

    flavor_name = Matcher(FLAVORS).pick_best_flavor(machine)
    if not flavor_name:
        raise Exception(
            f"Machine: {machine} could not be classified into any flavor {FLAVORS=}"
        )
    logger.info(f"Device has been classified as flavor: {flavor_name.name}")

    return flavor_name.name
