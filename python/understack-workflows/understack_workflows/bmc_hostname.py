from understack_workflows.bmc import Bmc
from understack_workflows.helpers import setup_logger

REDFISH_PATH = "/redfish/v1/Managers/iDRAC.Embedded.1/EthernetInterfaces/NIC.1"

logger = setup_logger(__name__)


def bmc_set_hostname(bmc: Bmc, current_name: str, new_name: str):
    """Set the hostname if required."""
    if not bmc or not current_name or not new_name:
        raise ValueError("Invalid input parameters")

    if current_name == new_name:
        logger.info("BMC hostname is already set to {new_name}")
        return

    logger.info(f"Changing BMC hostname from {current_name} to {new_name}")
    payload = {"HostName": new_name}
    bmc.redfish_request(REDFISH_PATH, method="PATCH", payload=payload)
