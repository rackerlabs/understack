from understack_workflows.bmc import Bmc
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


def bmc_set_permanent_ip_addr(bmc: Bmc, interface_info: InterfaceInfo):
    """If this device has DHCP IP configuration, configure it permanently."""
    if not bmc or not interface_info:
        raise ValueError("Invalid input parameters")

    if not interface_info.dhcp:
        logger.info("BMC interface was not set to DHCP")
        return

    if not (interface_info.ipv4_address and interface_info.ipv4_gateway):
        raise ValueError("BMC InterfaceInfo has missing IP information")

    payload = {
        "Attributes": {
            "IPv4.1.DHCPEnable": "Disabled",
            "IPv4.1.Address": str(interface_info.ipv4_address.ip),
            "IPv4.1.Gateway": str(interface_info.ipv4_gateway),
            "IPv4.1.Netmask": str(interface_info.ipv4_address.netmask),
        }
    }
    logger.info(
        "BMC was DHCP IP %s, making this permanent", interface_info.ipv4_address
    )
    attribute_path = bmc.manager_path + "/Attributes"
    bmc.redfish_request(attribute_path, method="PATCH", payload=payload)
