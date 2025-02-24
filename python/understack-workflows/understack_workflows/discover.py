import time

from understack_workflows.bmc import Bmc
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import chassis_info
from understack_workflows.bmc_power import bmc_power_on
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

MIN_REQUIRED_NEIGHBOR_COUNT = 3
LLDP_DISCOVERY_ATTEMPTS = 6


def discover_chassis_info(bmc: Bmc) -> ChassisInfo:
    """Query redfish, retrying until we get data that is acceptable.

    If the server is off, power it on.

    Make sure that we have at least MIN_REQUIRED_NEIGHBOR_COUNT LLDP neighbors
    in the returned ChassisInfo.  If that can't be achieved in a reasonable time
    then raise an Exception.
    """
    device_info = chassis_info(bmc)

    if not device_info.power_on:
        logger.info("Server is powered off, sending power-on command to %s", bmc)
        bmc_power_on(bmc)

    attempts_remaining = LLDP_DISCOVERY_ATTEMPTS
    while len(device_info.neighbors) < MIN_REQUIRED_NEIGHBOR_COUNT:
        logger.info(
            "%s does not have enough LLDP neighbors (saw %d), need at least %d. ",
            bmc,
            len(device_info.neighbors),
            MIN_REQUIRED_NEIGHBOR_COUNT,
        )
        if not attempts_remaining:
            raise Exception(
                f"Only {len(device_info.neighbors)} LLDP neighbors appeared, "
                f" but {MIN_REQUIRED_NEIGHBOR_COUNT} are required."
            )
        logger.info("Retry in 30 seconds (attempts_remaining=%d)", attempts_remaining)
        attempts_remaining = attempts_remaining - 1

        time.sleep(30)
        device_info = chassis_info(bmc)

    return device_info
