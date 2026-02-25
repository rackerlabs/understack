from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.pxe_port_heuristic import guess_pxe_interface


def test_integrated_is_best():
    x = "test"
    device_info = ChassisInfo(
        manufacturer=x,
        model_number=x,
        serial_number=x,
        bmc_ip_address=x,
        bios_version=x,
        power_on=False,
        memory_gib=0,
        cpu=x,
        interfaces=[
            InterfaceInfo("iDRAC", x, x),
            InterfaceInfo("NIC.Embedded.1-1", x, x),
            InterfaceInfo("NIC.Embedded.1-2", x, x),
            InterfaceInfo("NIC.Integrated.1-1", x, x),
            InterfaceInfo("NIC.Integrated.1-2", x, x),
            InterfaceInfo("NIC.Slot.1-1", x, x),
            InterfaceInfo("NIC.Slot.1-2", x, x),
        ],
    )
    assert guess_pxe_interface(device_info) == "NIC.Integrated.1-1"


def test_slot_is_second_best():
    x = "test"
    device_info = ChassisInfo(
        manufacturer=x,
        model_number=x,
        serial_number=x,
        bmc_ip_address=x,
        bios_version=x,
        power_on=False,
        memory_gib=0,
        cpu=x,
        interfaces=[
            InterfaceInfo("iDRAC", x, x),
            InterfaceInfo("NIC.Embedded.1-1", x, x),
            InterfaceInfo("NIC.Embedded.1-2", x, x),
            InterfaceInfo("NIC.Slot.1-2", x, x),
            InterfaceInfo("NIC.Slot.1-1", x, x),
            InterfaceInfo("NIC.Slot.2-2", x, x),
            InterfaceInfo("NIC.Slot.2-1", x, x),
        ],
    )
    assert guess_pxe_interface(device_info) == "NIC.Slot.1-1"


def test_connected_is_better():
    x = "test"
    device_info = ChassisInfo(
        manufacturer=x,
        model_number=x,
        serial_number=x,
        bmc_ip_address=x,
        bios_version=x,
        power_on=False,
        memory_gib=0,
        cpu=x,
        interfaces=[
            InterfaceInfo("iDRAC", x, x, remote_switch_port_name=x),
            InterfaceInfo("NIC.Embedded.1-1", x, x, remote_switch_port_name=x),
            InterfaceInfo("NIC.Embedded.1-1", x, x, remote_switch_port_name=x),
            InterfaceInfo("NIC.Integrated.1-1", x, x, remote_switch_port_name=None),
            InterfaceInfo("NIC.Integrated.1-2", x, x, remote_switch_port_name=None),
            InterfaceInfo("NIC.Slot.1-1", x, x, remote_switch_port_name=None),
            InterfaceInfo("NIC.Slot.1-2", x, x, remote_switch_port_name=x),
        ],
    )
    assert guess_pxe_interface(device_info) == "NIC.Slot.1-2"
