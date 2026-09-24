from ironic_understack.drivers.netdev_hardware import NetdevHardware
from ironic_understack.drivers.panos_hardware import PanosHardware


def _interface_names(ifaces):
    return [cls.__name__ for cls in ifaces]


def test_panos_is_a_netdev():
    # A PAN-OS appliance is a network device; the separate hardware type
    # exists so it is identifiable from the driver alone.
    assert issubclass(PanosHardware, NetdevHardware)


def test_panos_matches_netdev_interfaces_today():
    # Nothing diverges yet. This pins that, so adding a real inspect or deploy
    # interface later is a deliberate change rather than an accident.
    pa = PanosHardware()
    netdev = NetdevHardware()
    for name in (
        "supported_bios_interfaces",
        "supported_boot_interfaces",
        "supported_console_interfaces",
        "supported_deploy_interfaces",
        "supported_firmware_interfaces",
        "supported_inspect_interfaces",
        "supported_management_interfaces",
        "supported_network_interfaces",
        "supported_power_interfaces",
        "supported_raid_interfaces",
        "supported_rescue_interfaces",
        "supported_storage_interfaces",
        "supported_vendor_interfaces",
    ):
        assert getattr(pa, name) == getattr(netdev, name), name


def test_panos_deploy_is_noop():
    hw = PanosHardware()
    assert _interface_names(hw.supported_deploy_interfaces) == ["NoDeploy"]


def test_panos_network_is_neutron():
    hw = PanosHardware()
    assert _interface_names(hw.supported_network_interfaces) == ["NeutronNetwork"]
