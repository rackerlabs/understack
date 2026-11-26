from ironic.drivers.modules import noop

from ironic_understack.drivers.cisco_nxos_firmware import CiscoNxosFirmware
from ironic_understack.drivers.cisco_nxos_inspect import CiscoNxosInspect
from ironic_understack.drivers.netdev_hardware import NetdevHardware


class CiscoNxosHardware(NetdevHardware):
    """Hardware type for Cisco NX-OS (Nexus) switches.

    A :class:`NetdevHardware` with NX-OS firmware and inspect interfaces, which
    read the switch over NX-API without changing it. The netdev no-op
    interfaces stay supported as fallbacks.
    """

    @property
    def supported_firmware_interfaces(self):
        return [CiscoNxosFirmware, noop.NoFirmware]

    @property
    def supported_inspect_interfaces(self):
        return [CiscoNxosInspect, noop.NoInspect]
