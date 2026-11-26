from ironic_understack.drivers.cisco_nxos_hardware import CiscoNxosHardware
from ironic_understack.drivers.netdev_hardware import NetdevHardware


def _interface_names(ifaces):
    return [cls.__name__ for cls in ifaces]


def test_cisco_nxos_is_a_netdev():
    assert issubclass(CiscoNxosHardware, NetdevHardware)


def test_cisco_nxos_matches_netdev_except_inspect_and_firmware():
    hw = CiscoNxosHardware()
    netdev = NetdevHardware()
    for name in (
        "supported_bios_interfaces",
        "supported_boot_interfaces",
        "supported_console_interfaces",
        "supported_deploy_interfaces",
        "supported_management_interfaces",
        "supported_network_interfaces",
        "supported_power_interfaces",
        "supported_raid_interfaces",
        "supported_rescue_interfaces",
        "supported_storage_interfaces",
        "supported_vendor_interfaces",
    ):
        assert getattr(hw, name) == getattr(netdev, name), name


def test_cisco_nxos_inspect_and_firmware_default_to_cisco_nxos():
    hw = CiscoNxosHardware()
    assert _interface_names(hw.supported_inspect_interfaces) == [
        "CiscoNxosInspect",
        "NoInspect",
    ]
    assert _interface_names(hw.supported_firmware_interfaces) == [
        "CiscoNxosFirmware",
        "NoFirmware",
    ]
