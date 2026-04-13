from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.pxe_port_heuristic import guess_pxe_interfaces


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
    assert guess_pxe_interfaces(device_info) == [
        "NIC.Integrated.1-1",
        "NIC.Slot.1-1",
        "NIC.Integrated.1-2",
        "NIC.Slot.1-2",
    ]


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
    assert guess_pxe_interfaces(device_info) == [
        "NIC.Slot.1-1",
        "NIC.Slot.2-1",
        "NIC.Slot.1-2",
        "NIC.Slot.2-2",
    ]


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
            InterfaceInfo("iDRAC", x, x, remote_switch_mac_address=x),
            InterfaceInfo("NIC.Embedded.1-1", x, x, remote_switch_mac_address=x),
            InterfaceInfo("NIC.Embedded.1-1", x, x, remote_switch_mac_address=x),
            InterfaceInfo("NIC.Integrated.1-1", x, x, remote_switch_mac_address=None),
            InterfaceInfo("NIC.Integrated.1-2", x, x, remote_switch_mac_address=None),
            InterfaceInfo("NIC.Slot.1-1", x, x, remote_switch_mac_address=None),
            InterfaceInfo("NIC.Slot.1-2", x, x, remote_switch_mac_address=x),
        ],
    )
    assert guess_pxe_interfaces(device_info) == [
        "NIC.Slot.1-2",
        "NIC.Integrated.1-1",
        "NIC.Slot.1-1",
        "NIC.Integrated.1-2",
    ]


def test_connected_macs_picks_first():
    any_mac = "00:00:00:00:00:00"
    pxe_mac = "11:22:33:44:55:66"
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
            InterfaceInfo("iDRAC", x, x, remote_switch_mac_address=x),
            InterfaceInfo("NIC.Embedded.1-1", x, x, remote_switch_mac_address=None),
            InterfaceInfo("NIC.Embedded.1-1", x, x, remote_switch_mac_address=any_mac),
            InterfaceInfo(
                "NIC.Integrated.1-1", x, x, remote_switch_mac_address=any_mac
            ),
            InterfaceInfo(
                "NIC.Integrated.1-2", x, x, remote_switch_mac_address=any_mac
            ),
            InterfaceInfo("NIC.Slot.1-1", x, x, remote_switch_mac_address=any_mac),
            InterfaceInfo("NIC.Slot.1-2", x, x, remote_switch_mac_address=any_mac),
        ],
    )
    assert guess_pxe_interfaces(device_info, {pxe_mac}) == [
        "NIC.Integrated.1-1",
        "NIC.Slot.1-1",
        "NIC.Integrated.1-2",
        "NIC.Slot.1-2",
    ]


def test_connected_to_known_pxe_is_best():
    any_mac = "00:00:00:00:00:00"
    pxe_mac = "11:22:33:44:55:66"
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
            InterfaceInfo("iDRAC", x, x, remote_switch_mac_address=x),
            InterfaceInfo("NIC.Embedded.1-1", x, x, remote_switch_mac_address=None),
            InterfaceInfo("NIC.Embedded.1-1", x, x, remote_switch_mac_address=any_mac),
            InterfaceInfo(
                "NIC.Integrated.1-1", x, x, remote_switch_mac_address=any_mac
            ),
            InterfaceInfo(
                "NIC.Integrated.1-2", x, x, remote_switch_mac_address=any_mac
            ),
            InterfaceInfo("NIC.Slot.1-1", x, x, remote_switch_mac_address=pxe_mac),
            InterfaceInfo("NIC.Slot.1-2", x, x, remote_switch_mac_address=pxe_mac),
        ],
    )
    assert guess_pxe_interfaces(device_info, {pxe_mac}) == [
        "NIC.Slot.1-1",
        "NIC.Slot.1-2",
        "NIC.Integrated.1-1",
        "NIC.Integrated.1-2",
    ]
