from ipaddress import IPv4Address
from ipaddress import IPv4Interface

from understack_workflows.bmc import Bmc
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.bmc_network_config import bmc_set_permanent_ip_addr


def _dhcp_interface():
    return InterfaceInfo(
        name="iDRAC",
        description="Dedicated iDRAC interface",
        mac_address="6C:3C:8C:A9:6C:6C",
        ipv4_address=IPv4Interface("10.46.104.7/23"),
        ipv4_gateway=IPv4Address("10.46.104.1"),
        dhcp=True,
    )


def test_set_permanent_ip_uses_static_attributes_for_idrac10(mocker):
    attribute_path = (
        "/redfish/v1/Managers/iDRAC.Embedded.1/Oem/Dell/DellAttributes/iDRAC.Embedded.1"
    )
    bmc = mocker.Mock(spec=Bmc)
    bmc.manager_attributes_path = attribute_path

    bmc_set_permanent_ip_addr(bmc, _dhcp_interface())

    bmc.redfish_request.assert_called_once_with(
        attribute_path,
        method="PATCH",
        payload={
            "Attributes": {
                "IPv4.1.DHCPEnable": "Disabled",
                "IPv4.1.StaticAddress": "10.46.104.7",
                "IPv4.1.StaticGateway": "10.46.104.1",
                "IPv4.1.StaticNetmask": "255.255.254.0",
            }
        },
    )


def test_set_permanent_ip_keeps_legacy_idrac9_patch(mocker):
    attribute_path = "/redfish/v1/Managers/iDRAC.Embedded.1/Attributes"
    bmc = mocker.Mock(spec=Bmc)
    bmc.manager_attributes_path = attribute_path

    bmc_set_permanent_ip_addr(bmc, _dhcp_interface())

    bmc.redfish_request.assert_called_once_with(
        attribute_path,
        method="PATCH",
        payload={
            "Attributes": {
                "IPv4.1.DHCPEnable": "Disabled",
                "IPv4.1.Address": "10.46.104.7",
                "IPv4.1.Gateway": "10.46.104.1",
                "IPv4.1.Netmask": "255.255.254.0",
            }
        },
    )
