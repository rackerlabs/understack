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
"""PAN-OS Management Interface for Palo Alto firewalls."""

from ironic.drivers import base
from ironic.drivers.modules import noop_mgmt
from oslo_log import log

LOG = log.getLogger(__name__)


class PanosManagement(noop_mgmt.NoopManagement):
    """Management interface for PAN-OS firewalls.

    Provides lifecycle management operations for Palo Alto firewalls:
    - Initial configuration setup (verify step during enroll->manageable)
    - Factory reset / configuration cleanup (clean step)
    - Future: firmware updates, configuration backups, etc.

    Inherits from NoopManagement to get sensible defaults for boot device
    methods (which don't apply to network appliances).
    """

    def get_properties(self):
        """Return the properties of the interface.

        :returns: dictionary of <property name>:<property description> entries.
        """
        return {
            "panos_address": "Management IP address or hostname for API access. "
            "Required. Example: 10.15.149.46",
            "panos_username": 'API username. Required. Usually "admin".',
            "panos_password": "API password. Required.",
            "panos_verify_ssl": "Whether to verify SSL certificates. "
            "Optional, defaults to False.",
            # Initial setup parameters (used by verify step)
            "panos_management_ip": "Management IP to configure on device. "
            "Optional, only used during initial setup.",
            "panos_management_netmask": "Management netmask. "
            "Optional, only used during initial setup.",
            "panos_management_gateway": "Management gateway. "
            "Optional, only used during initial setup.",
        }

    def validate(self, task):
        """Validate that required credentials are present.

        :param task: a TaskManager instance.
        :raises: MissingParameterValue if required parameters are missing.
        """
        # TODO: Implement validation
        # Check panos_address, panos_username, panos_password

    @base.verify_step(priority=10)
    def setup_initial_configuration(self, task):
        """Perform initial configuration setup for a new firewall.

        This verify step runs during the enroll->manageable transition
        for brand new firewalls. It performs first-time setup:

        1. Configure management interface (IP, netmask, gateway)
        2. Remove factory default configurations that conflict:
           - Default security rule 'rule1'
           - Default zones 'trust' and 'untrust'
           - Default virtual-wire 'default-vwire'
           - Default interface configs on ethernet1/1, ethernet1/2
        3. Configure jumbo frames (if needed)
        4. Set admin credentials
        5. Set hostname
        6. Commit all changes

        This step is ONLY for initial setup. It should be idempotent
        (safe to run multiple times) and should detect if setup is
        already complete.

        :param task: a TaskManager instance.
        :returns: None (synchronous operation)
        :raises: Exception if setup fails
        """
        node = task.node
        LOG.info("[node:%s] Starting initial PAN-OS configuration setup", node.uuid)

        # TODO: Get connection and setup parameters from driver_info
        # address = node.driver_info.get('panos_address')
        # username = node.driver_info.get('panos_username')
        # password = node.driver_info.get('panos_password')
        # mgmt_ip = node.driver_info.get('panos_management_ip')
        # mgmt_netmask = node.driver_info.get('panos_management_netmask')
        # mgmt_gateway = node.driver_info.get('panos_management_gateway')

        try:
            # TODO: Connect to device
            # session = _build_panos_session(verify_ssl)
            # api_key = _get_api_key(address, username, password, session)

            # TODO: Check if initial setup is already complete
            # If device is already configured, skip
            # is_configured = _check_if_configured(address, api_key, session)
            # if is_configured:
            #     LOG.info('[node:%s] Device already configured, skipping setup',
            #              node.uuid)
            #     return

            # TODO: Configure management interface
            # if mgmt_ip and mgmt_netmask and mgmt_gateway:
            #     _configure_management_interface(
            #         address, api_key, session, mgmt_ip, mgmt_netmask, mgmt_gateway
            #     )
            #     LOG.info('[node:%s] Configured management interface', node.uuid)

            # TODO: Remove factory defaults
            # _remove_factory_defaults(address, api_key, session)
            # LOG.info('[node:%s] Removed factory default configuration', node.uuid)

            # TODO: Configure jumbo frames
            # _configure_jumbo_frames(address, api_key, session)
            # LOG.info('[node:%s] Configured jumbo frames', node.uuid)

            # TODO: Set hostname (from node name or properties)
            # hostname = node.name or node.properties.get('hostname')
            # if hostname:
            #     _set_hostname(address, api_key, session, hostname)
            #     LOG.info('[node:%s] Set hostname to %s', node.uuid, hostname)

            # TODO: Commit all changes
            # _commit_config(address, api_key, session,
            #               description='Initial device setup')
            # LOG.info('[node:%s] Committed initial configuration', node.uuid)

            LOG.info("[node:%s] Initial configuration setup completed", node.uuid)
            # TODO: Remove when implemented

        except Exception as e:
            msg = f"Initial configuration setup failed for node {node.uuid}: {e}"
            LOG.exception(msg)
            raise

    @base.clean_step(priority=10, requires_ramdisk=False)
    def reset_to_factory_defaults(self, task):
        """Reset firewall to factory defaults.

        This clean step runs during the cleaning phase (between tenant uses
        or on-demand). It performs a full configuration reset:

        1. Backup current configuration (optional)
        2. Execute factory reset command
        3. Wait for reboot
        4. Re-run initial setup (via setup_initial_configuration)

        WARNING: This is destructive and should only run during cleaning.

        :param task: a TaskManager instance.
        :returns: None (synchronous) or states.CLEANWAIT (asynchronous)
        :raises: Exception if reset fails
        """
        node = task.node
        LOG.info("[node:%s] Starting factory reset", node.uuid)

        # TODO: Implement factory reset
        # This is a future feature - not needed for initial implementation
        # For now, just log and skip

        LOG.warning("[node:%s] Factory reset not yet implemented, skipping", node.uuid)

    @base.clean_step(priority=5, requires_ramdisk=False, abortable=True, argsinfo={})
    def clear_configuration(self, task):
        """Clear specific configuration sections without full factory reset.

        This clean step removes configuration that should not persist
        between tenants:
        - Security policies
        - NAT rules
        - Custom zones
        - Custom interfaces
        - Custom routing

        Preserves:
        - Management interface configuration
        - Admin credentials
        - Basic system settings

        :param task: a TaskManager instance.
        :returns: None
        :raises: Exception if cleaning fails
        """
        node = task.node
        LOG.info("[node:%s] Starting configuration cleanup", node.uuid)

        # TODO: Implement selective configuration cleanup
        # This is a future feature for between-tenant cleaning

        LOG.warning(
            "[node:%s] Configuration cleanup not yet implemented, skipping", node.uuid
        )


# TODO: Implement helper functions for configuration operations


def _check_if_configured(address, api_key, session):
    """Check if device has already been configured (not factory fresh).

    :returns: bool, True if configured, False if factory fresh
    """
    # TODO: Implement
    # - Query for presence of specific config elements
    # - Check if management IP is set
    # - Check if default rules/zones are gone


def _configure_management_interface(
    address, api_key, session, mgmt_ip, netmask, gateway
):
    """Configure management interface with IP/netmask/gateway.

    :param mgmt_ip: Management IP address
    :param netmask: Netmask
    :param gateway: Default gateway
    """
    # TODO: Implement
    # - Set management IP via config API
    # - Set netmask
    # - Set default gateway
    # - DO NOT commit (caller will commit all changes together)


def _remove_factory_defaults(address, api_key, session):
    """Remove factory default configuration that conflicts with production use.

    Removes:
    - Default security rule 'rule1'
    - Default zones 'trust' and 'untrust'
    - Default virtual-wire 'default-vwire'
    - Default interface configs on ethernet1/1, ethernet1/2
    """
    # TODO: Implement
    # For each default config element:
    # - Build xpath
    # - Execute delete command
    # - Log success/skip
    # - DO NOT commit (caller will commit all changes together)


def _configure_jumbo_frames(address, api_key, session):
    """Configure jumbo frame support on all interfaces.

    :param address: Management IP or hostname
    :param api_key: API key
    :param session: requests.Session
    """
    # TODO: Implement
    # - Query interfaces
    # - For each interface, set MTU to 9000 (or configured value)
    # - DO NOT commit (caller will commit all changes together)


def _set_hostname(address, api_key, session, hostname):
    """Set device hostname.

    :param hostname: Hostname to set
    """
    # TODO: Implement
    # - Set hostname via config API
    # - DO NOT commit (caller will commit all changes together)


def _commit_config(address, api_key, session, description=None):
    """Commit configuration changes and wait for completion.

    :param description: Optional commit description
    :raises: Exception if commit fails or times out
    """
    # TODO: Implement
    # - Execute commit command with description
    # - Get job ID
    # - Poll job status until complete
    # - Raise exception if commit fails
