from understack_workflows.topology import pxe_interface_name
from understack_workflows.topology import switch_connections


def test_pxe_interface_name(dell_nautobot_device):
    assert pxe_interface_name(dell_nautobot_device) == "NIC.Slot.1-2"


def test_switch_connections(dell_nautobot_device):
    assert switch_connections(dell_nautobot_device) == {
        "NIC.Integrated.1-1": "f20-2-1.iad3.rackspace.net",
        "NIC.Integrated.1-2": "f20-2-2.iad3.rackspace.net",
        "NIC.Slot.1-1": "f20-2-2.iad3.rackspace.net",
        "NIC.Slot.1-2": "f20-2-1.iad3.rackspace.net",
        "iDRAC": "f20-2-1d.iad3.rackspace.net",
    }
