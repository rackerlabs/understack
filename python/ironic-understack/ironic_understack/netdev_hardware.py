from ironic.drivers import generic
from ironic.drivers.modules import noop
from ironic.drivers.modules.network import neutron
from ironic.drivers.modules.storage import noop as noop_storage


class NetdevHardware(generic.ManualManagementHardware):
    """Hardware type for network devices.

    Intended for nodes that represent network infrastructure (e.g. switches,
    routers). Deploy is intentionally a no-op; Neutron is the only supported
    network interface. All other interfaces use the no-* noop variants.

    Boot, power, and management are inherited from ManualManagementHardware
    (NoopManagement / FakePower / iPXE+PXE boot) because Ironic has no
    NoBoot or NoPower equivalents.
    """

    @property
    def supported_bios_interfaces(self):
        return [noop.NoBIOS]

    @property
    def supported_console_interfaces(self):
        return [noop.NoConsole]

    @property
    def supported_deploy_interfaces(self):
        return [noop.NoDeploy]

    @property
    def supported_firmware_interfaces(self):
        return [noop.NoFirmware]

    @property
    def supported_inspect_interfaces(self):
        return [noop.NoInspect]

    @property
    def supported_network_interfaces(self):
        return [neutron.NeutronNetwork]

    @property
    def supported_raid_interfaces(self):
        return [noop.NoRAID]

    @property
    def supported_rescue_interfaces(self):
        return [noop.NoRescue]

    @property
    def supported_storage_interfaces(self):
        return [noop_storage.NoopStorage]

    @property
    def supported_vendor_interfaces(self):
        return [noop.NoVendor]
