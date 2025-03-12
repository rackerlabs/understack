import pytest

from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.topology import pxe_interface_name
from understack_workflows.topology import switch_connections

alien_int = InterfaceInfo(
    name="NIC.Slot.1-1",
    description="",
    mac_address="11:22:33:44:55:66",
    remote_switch_mac_address="AA:AA:AA:AA:AA:AA",
    remote_switch_port_name="Eth1/1",
)

goodint1 = InterfaceInfo(
    name="NIC.Slot.1-2",
    description="",
    mac_address="11:22:33:44:55:66",
    remote_switch_mac_address="C4:7E:E0:E3:EC:2B",
    remote_switch_port_name="Eth1/2",
)

goodint2 = InterfaceInfo(
    name="iDRAC",
    description="",
    mac_address="11:22:33:44:55:66",
    remote_switch_mac_address="C4:B3:6A:C8:33:80",
    remote_switch_port_name="Eth1/3",
)


def test_pxe_interface_name_unknown_switch():
    with pytest.raises(ValueError):
        pxe_interface_name([alien_int])


def test_pxe_interface_name():
    assert pxe_interface_name([goodint1, goodint2]) == "NIC.Slot.1-2"


def test_switch_connections():
    assert switch_connections([goodint1, goodint2]) == {
        "NIC.Slot.1-2": "f20-1-1.iad3.rackspace.net",
        "iDRAC": "f20-3-1d.iad3.rackspace.net",
    }
