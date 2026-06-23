from ironic.drivers.modules import noop
from ironic.drivers.modules.storage import noop as noop_storage

from ironic_understack.netdev_hardware import NetdevHardware


def _interface_names(ifaces):
    return [cls.__name__ for cls in ifaces]


def test_netdev_deploy():
    hw = NetdevHardware()
    assert _interface_names(hw.supported_deploy_interfaces) == ["NoDeploy"]


def test_netdev_bios():
    hw = NetdevHardware()
    assert _interface_names(hw.supported_bios_interfaces) == ["NoBIOS"]


def test_netdev_network():
    hw = NetdevHardware()
    assert _interface_names(hw.supported_network_interfaces) == ["NeutronNetwork"]


def test_netdev_noop_interfaces():
    hw = NetdevHardware()
    assert hw.supported_console_interfaces == [noop.NoConsole]
    assert hw.supported_firmware_interfaces == [noop.NoFirmware]
    assert hw.supported_inspect_interfaces == [noop.NoInspect]
    assert hw.supported_raid_interfaces == [noop.NoRAID]
    assert hw.supported_rescue_interfaces == [noop.NoRescue]
    assert hw.supported_storage_interfaces == [noop_storage.NoopStorage]
    assert hw.supported_vendor_interfaces == [noop.NoVendor]
