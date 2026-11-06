import logging

from understack_workflows.bmc import Bmc
from understack_workflows.bmc_chassis_info import InterfaceInfo

logger = logging.getLogger(__name__)


def bmc_set_permanent_ip_addr(bmc: Bmc, interface_info: InterfaceInfo):
    """If this device has DHCP IP configuration, configure it permanently."""
    if not bmc or not interface_info:
        raise ValueError("Invalid input parameters")

    if not interface_info.dhcp:
        logger.info("BMC interface was not set to DHCP")
        return

    if not (interface_info.ipv4_address and interface_info.ipv4_gateway):
        raise ValueError("BMC InterfaceInfo has missing IP information")

    logger.info(
        "BMC was DHCP IP %s, making this permanent", interface_info.ipv4_address
    )
    attribute_path = bmc.manager_attributes_path
    uses_idrac10_attributes = not attribute_path.rstrip("/").endswith("/Attributes")
    address_key = (
        "IPv4.1.StaticAddress" if uses_idrac10_attributes else "IPv4.1.Address"
    )
    gateway_key = (
        "IPv4.1.StaticGateway" if uses_idrac10_attributes else "IPv4.1.Gateway"
    )
    netmask_key = (
        "IPv4.1.StaticNetmask" if uses_idrac10_attributes else "IPv4.1.Netmask"
    )

    bmc.redfish_request(
        attribute_path,
        method="PATCH",
        payload={
            "Attributes": {
                "IPv4.1.DHCPEnable": "Disabled",
                address_key: str(interface_info.ipv4_address.ip),
                gateway_key: str(interface_info.ipv4_gateway),
                netmask_key: str(interface_info.ipv4_address.netmask),
            }
        },
    )
