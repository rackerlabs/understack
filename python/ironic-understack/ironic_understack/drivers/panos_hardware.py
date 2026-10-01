from ironic.drivers.modules import noop
from ironic.drivers.modules import noop_mgmt

from ironic_understack.drivers.netdev_hardware import NetdevHardware
from ironic_understack.drivers.panos_inspect import PanosInspect
from ironic_understack.drivers.panos_management import PanosManagement


class PanosHardware(NetdevHardware):
    """Hardware type for PAN-OS (Palo Alto) network appliances.

    A :class:`NetdevHardware` with PAN-OS inspect and management interfaces,
    which talk to the appliance over its XML API. The netdev no-op interfaces
    stay supported as fallbacks.
    """

    @property
    def supported_inspect_interfaces(self):
        return [PanosInspect, noop.NoInspect]

    @property
    def supported_management_interfaces(self):
        return [PanosManagement, noop_mgmt.NoopManagement]
