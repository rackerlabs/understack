"""Tests for PAN-OS hardware type."""

from ironic.drivers.modules import noop
from ironic.drivers.modules.storage import noop as noop_storage

from ironic_understack.drivers.panos_hardware import PanosHardware


def _interface_names(ifaces):
    """Extract class names from interface list."""
    return [cls.__name__ for cls in ifaces]


def test_panos_hardware_type_exists():
    """Test that PanosHardware can be instantiated."""
    hw = PanosHardware()
    assert hw is not None


def test_panos_inspect_interface():
    """Test that PanosInspect is the supported inspect interface."""
    hw = PanosHardware()
    assert _interface_names(hw.supported_inspect_interfaces) == ["PanosInspect"]


def test_panos_management_interface():
    """Test that PanosManagement is the supported management interface."""
    hw = PanosHardware()
    assert _interface_names(hw.supported_management_interfaces) == ["PanosManagement"]


def test_panos_deploy_interface():
    """Test that NoDeploy is used (firewalls don't deploy)."""
    hw = PanosHardware()
    assert _interface_names(hw.supported_deploy_interfaces) == ["NoDeploy"]


def test_panos_network_interface():
    """Test that NeutronNetwork is the supported network interface."""
    hw = PanosHardware()
    assert _interface_names(hw.supported_network_interfaces) == ["NeutronNetwork"]


def test_panos_bios_interface():
    """Test that NoBIOS is used (firewalls don't have BIOS config)."""
    hw = PanosHardware()
    assert _interface_names(hw.supported_bios_interfaces) == ["NoBIOS"]


def test_panos_noop_interfaces():
    """Test that appropriate noop interfaces are used."""
    hw = PanosHardware()
    assert hw.supported_console_interfaces == [noop.NoConsole]
    assert hw.supported_firmware_interfaces == [noop.NoFirmware]
    assert hw.supported_raid_interfaces == [noop.NoRAID]
    assert hw.supported_rescue_interfaces == [noop.NoRescue]
    assert hw.supported_storage_interfaces == [noop_storage.NoopStorage]
    assert hw.supported_vendor_interfaces == [noop.NoVendor]
