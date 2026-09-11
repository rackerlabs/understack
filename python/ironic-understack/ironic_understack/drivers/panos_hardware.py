# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""PAN-OS Hardware Type for Palo Alto firewalls."""

from ironic.drivers import generic
from ironic.drivers.modules import noop
from ironic.drivers.modules.network import neutron
from ironic.drivers.modules.storage import noop as noop_storage

from ironic_understack.drivers import panos_inspect
from ironic_understack.drivers import panos_management


class PanosHardware(generic.ManualManagementHardware):
    """Hardware type for Palo Alto (PAN-OS) firewalls.

    Intended for nodes that represent Palo Alto firewall appliances
    (PA-1410, PA-5410, etc.). These devices:
    - Have no deploy ramdisk
    - Are managed via PAN-OS XML API
    - Use Neutron for network port binding
    - Require custom inspect and management interfaces

    All other interfaces (boot, power, deploy, raid, etc.) use no-op
    implementations since they don't apply to firewall appliances.

    Boot and power are inherited from ManualManagementHardware, which
    uses FakePower (power state controlled by manual operator) since
    there's no automated power management for these devices.
    """

    @property
    def supported_bios_interfaces(self):
        """No BIOS on firewall appliances."""
        return [noop.NoBIOS]

    @property
    def supported_console_interfaces(self):
        """Console access not supported via Ironic for PAN-OS."""
        return [noop.NoConsole]

    @property
    def supported_deploy_interfaces(self):
        """No image deployment for firewall appliances."""
        return [noop.NoDeploy]

    @property
    def supported_firmware_interfaces(self):
        """Firmware updates handled separately."""
        return [noop.NoFirmware]

    @property
    def supported_inspect_interfaces(self):
        """Use custom PAN-OS inspect interface for hardware discovery."""
        return [panos_inspect.PanosInspect]

    @property
    def supported_management_interfaces(self):
        """Use custom PAN-OS management interface for lifecycle operations."""
        return [panos_management.PanosManagement]

    @property
    def supported_network_interfaces(self):
        """Use Neutron for network port binding."""
        return [neutron.NeutronNetwork]

    @property
    def supported_raid_interfaces(self):
        """No RAID on firewall appliances."""
        return [noop.NoRAID]

    @property
    def supported_rescue_interfaces(self):
        """Rescue mode not applicable to firewall appliances."""
        return [noop.NoRescue]

    @property
    def supported_storage_interfaces(self):
        """No storage management for firewall appliances."""
        return [noop_storage.NoopStorage]

    @property
    def supported_vendor_interfaces(self):
        """No vendor-specific passthrough needed."""
        return [noop.NoVendor]
