import logging

from understack_workflows.bmc import Bmc

logger = logging.getLogger(__name__)


def bmc_get_mgmt_interface(bmc: Bmc) -> str:
    """Read BMC interface."""
    return bmc.redfish_request(bmc.manager_path + "/EthernetInterfaces")["Members"][0][
        "@odata.id"
    ]


def bmc_set_hostname(bmc: Bmc, current_name: str, new_name: str):
    """Set the hostname if required."""
    if not bmc or not current_name or not new_name:
        raise ValueError("Invalid input parameters")

    if current_name == new_name:
        logger.info("BMC hostname is already set to %s", new_name)
        return

    logger.info("Changing BMC hostname from %s to %s", current_name, new_name)
    payload = {"HostName": new_name}
    interface_path = bmc_get_mgmt_interface(bmc)
    bmc.redfish_request(interface_path, method="PATCH", payload=payload)
