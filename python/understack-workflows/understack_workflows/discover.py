import time

from understack_workflows.bmc import Bmc
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import chassis_info
from understack_workflows.bmc_power import bmc_power_on
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

MIN_REQURED_NEIGHBOR_COUNT = 3


def discover_chassis_info(bmc: Bmc) -> ChassisInfo:
    """Query redfish, retrying until we get data that is acceptable.

    If the server is off, power it on.

    Make sure that we have at lease MIN_REQURED_NEIGHBOR_COUNT LLDP neighbors in
    the returned ChassisInfo.  If that can't be achieved in a reasonable time
    then raise an Exception.
    """
    device_info = chassis_info(bmc)

    if not device_info.power_on:
        logger.info(f"Server is powered off, sending power-on command to {bmc}")
        bmc_power_on(bmc)

    attempts_remaining = 6
    while len(device_info.neighbors) < MIN_REQURED_NEIGHBOR_COUNT:
        logger.info(
            f"{bmc} does not have enough LLDP neighbors "
            f"(saw {device_info.neighbors}), need at "
            f"least {MIN_REQURED_NEIGHBOR_COUNT}. "
        )
        if not attempts_remaining:
            raise Exception("No neighbors appeared")
        logger.info(f"Retry in 30 seconds ({attempts_remaining=})")
        attempts_remaining = attempts_remaining - 1

        time.sleep(30)
        device_info = chassis_info(bmc)

    return device_info
