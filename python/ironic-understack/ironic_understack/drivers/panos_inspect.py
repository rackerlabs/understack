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
"""PAN-OS Inspect Interface for Palo Alto firewalls."""

from typing import ClassVar

from ironic.common import exception
from ironic.common import states
from ironic.drivers import base
from oslo_log import log

LOG = log.getLogger(__name__)


class PanosInspect(base.InspectInterface):
    """Inspect interface for PAN-OS firewalls.

    Performs discovery and inspection of Palo Alto firewall hardware:
    - Queries system information (model, serial, version)
    - Discovers physical connectivity via LLDP
    - Creates Ironic Port objects for data plane interfaces
    - Discovers HA configuration and peer information

    This interface does NOT require a ramdisk - all operations are performed
    via the PAN-OS XML API over the management interface.
    """

    # Override default essential properties - firewalls don't have memory_mb/cpu_arch
    # in the traditional server sense
    ESSENTIAL_PROPERTIES: ClassVar[set] = set()

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
            "panos_api_port": "API port. Optional, defaults to 443.",
        }

    def validate(self, task):
        """Validate the driver_info contains required credentials.

        :param task: a TaskManager instance.
        :raises: MissingParameterValue if required parameters are missing.
        :raises: InvalidParameterValue if parameters are invalid.
        """
        driver_info = task.node.driver_info

        # TODO: Implement validation
        # Check that panos_address, panos_username, panos_password are present
        # Optionally validate that we can connect to the device

        missing = []
        if not driver_info.get("panos_address"):
            missing.append("panos_address")
        if not driver_info.get("panos_username"):
            missing.append("panos_username")
        if not driver_info.get("panos_password"):
            missing.append("panos_password")

        if missing:
            raise exception.MissingParameterValue(
                f'Missing required driver_info parameters: {", ".join(missing)}'
            )

    def inspect_hardware(self, task):
        """Inspect hardware to discover firewall properties.

        This method:
        1. Connects to the firewall via PAN-OS XML API
        2. Queries system information (show system info)
        3. Discovers interfaces and MAC addresses (show interface all)
        4. Performs LLDP discovery to identify physical connectivity:
           - Enables LLDP if not configured
           - Temporarily brings up unconfigured interfaces
           - Collects LLDP neighbor data
           - Restores original interface states
        5. Queries HA configuration (show high-availability all)
        6. Creates Ironic Port objects for discovered data plane interfaces
        7. Updates node.properties with discovered data

        :param task: a TaskManager instance.
        :raises: HardwareInspectionFailure if inspection fails.
        :returns: states.MANAGEABLE
        """
        node = task.node
        address = node.driver_info.get("management_ip")
        if not address:
            raise exception.InvalidParameterValue(
                "Node %s missing management_ip in driver_info"
            )

        LOG.info("[node:%s] Starting PAN-OS inspection", node.uuid)

        # TODO: Get connection details from driver_info
        # username = admin
        # password = from secrets https://github.com/RSS-Engineering/undercloud-deploy/pull/2141
        # verify_ssl = False

        try:
            # TODO: Connect to PAN-OS API
            # session = _build_panos_session(verify_ssl)
            # api_key = _get_api_key(address, username, password, session)
            # will need to try multiple creds options until one works

            # TODO: Collect system information
            # system_info = _collect_system_info(address, api_key, session)
            # LOG.debug('[node:%s] System info: %s', node.uuid, system_info)

            # TODO: Collect interface data
            # interfaces = _collect_interfaces(address, api_key, session)
            # LOG.debug('[node:%s] Found %d interfaces', node.uuid, len(interfaces))

            # TODO: Perform LLDP discovery
            # lldp_neighbors = _discover_lldp_neighbors(
            #     address, api_key, session, interfaces
            # )
            # LOG.info('[node:%s] Discovered %d LLDP neighbors',
            #          node.uuid, len(lldp_neighbors))

            # TODO: Query HA configuration
            # ha_config = _collect_ha_config(address, api_key, session)
            # if ha_config.get('enabled'):
            #     LOG.info('[node:%s] HA enabled, peer: %s',
            #              node.uuid, ha_config.get('peer_serial'))

            # TODO: Update node properties
            # node.properties['serial'] = system_info.get('serial')
            # node.properties['model'] = system_info.get('model')
            # node.properties['vendor'] = 'Palo Alto Networks'
            # node.properties['firmware_version'] = system_info.get('sw-version')
            # if ha_config.get('enabled'):
            #     node.extra['ha_peer_serial'] = ha_config.get('peer_serial')
            # node.save()

            # TODO: Create/update Ironic Port objects from LLDP neighbors
            # _create_ports_from_lldp(task, lldp_neighbors)

            LOG.info("[node:%s] PAN-OS inspection completed successfully", node.uuid)
            # TODO: Remove when implemented

        except Exception as e:
            msg = f"PAN-OS inspection failed for node {node.uuid}: {e}"
            LOG.exception(msg)
            raise exception.HardwareInspectionFailure(error=msg) from e

        return states.MANAGEABLE


# TODO: Implement helper functions for PAN-OS API operations
# These should be pure functions that take connection params and return data


def _build_panos_session(verify_ssl=False):
    """Build HTTP session for PAN-OS API.

    :param verify_ssl: Whether to verify SSL certificates
    :returns: requests.Session configured with retries
    """
    # TODO: Implement
    # - Create requests.Session
    # - Configure retries
    # - Set verify=verify_ssl


def _get_api_key(address, username, password, session):
    """Obtain API key from PAN-OS device.

    :param address: Management IP or hostname
    :param username: API username
    :param password: API password
    :param session: requests.Session
    :returns: API key string
    :raises: Exception if authentication fails
    """
    # TODO: Implement
    # - Call /api/?type=keygen
    # - Parse XML response for key


def _collect_system_info(address, api_key, session):
    """Collect system information from PAN-OS device.

    :param address: Management IP or hostname
    :param api_key: API key
    :param session: requests.Session
    :returns: dict with system info (hostname, serial, model, sw-version, etc.)
    """
    # TODO: Implement
    # - Execute: <show><system><info/></system></show>
    # - Parse XML response
    # - Return dict with all fields
    # Sample Data
    """
        admin@PA-1410> show system info
        hostname: PA-1410
        ip-address: 10.15.149.107
        public-ip-address: unknown
        netmask: 255.255.255.0
        default-gateway: 10.15.149.1
        ip-assignment: static
        ipv6-address: unknown
        ipv6-link-local-address: fe80::8e36:7aff:fe23:3a3a/64
        ipv6-default-gateway:
        mac-address: 8c:36:7a:23:3a:3a
        time: Fri Sep 11 12:13:31 2026
        uptime: 15 days, 21:59:46
        family: 1400
        model: PA-1410
        serial: 026701009879
        base_mac: 60:15:2b:61:1a:00
        mac_count: 254
        cloud-mode: non-cloud
        sw-version: 11.0.0
        global-protect-client-package-version: 0.0.0
        device-dictionary-version: 0
        device-dictionary-release-date:
        app-version: 8635-7675
        app-release-date:
        av-version: 0
        av-release-date:
        threat-version: 0
        threat-release-date:
        wf-private-version: 0
        wf-private-release-date: unknown
        url-db: paloaltonetworks
        wildfire-version: 0
        wildfire-release-date:
        wildfire-rt: Disabled
        url-filtering-version: 0000.00.00.000
        global-protect-datafile-version: unknown
        global-protect-datafile-release-date: unknown
        global-protect-clientless-vpn-version: 0
        global-protect-clientless-vpn-release-date:
        logdb-version: 11.0.0
        dlp: dlp-4.0.0
        platform-family: 1400
        vpn-disable-mode: off
        multi-vsys: off
        zero-touch-provisioning: Disabled
        operational-mode: normal
        advanced-routing: off
        device-certificate-status: None
    """


def _collect_interfaces(address, api_key, session):
    """Collect interface information including MAC addresses.

    :param address: Management IP or hostname
    :param api_key: API key
    :param session: requests.Session
    :returns: list of dicts with interface data (name, mac, state, speed, etc.)
    """
    # TODO: Implement
    # - Execute: <show><interface>all</interface></show>
    # - Parse hw entries for MAC addresses
    # - Return list of interface dicts


def _discover_lldp_neighbors(address, api_key, session, interfaces):
    """Perform LLDP discovery to identify physical connectivity.

    This is the "full discovery" mode that temporarily modifies configuration:
    1. Check if LLDP is already configured
    2. If not, enable LLDP globally
    3. Create LLDP profile (transmit-receive mode)
    4. Configure unconfigured interfaces with LLDP
    5. Wait for LLDP neighbors (30 seconds)
    6. Query LLDP neighbor data
    7. Restore original interface states
    8. Commit restoration

    :param address: Management IP or hostname
    :param api_key: API key
    :param session: requests.Session
    :param interfaces: list of interface dicts
    :returns: list of LLDP neighbor dicts (local_interface, local_mac,
              remote_chassis_id, remote_port_id, remote_system_name, etc.)
    """
    # TODO: Implement full LLDP discovery flow
    # This is where the logic from your current panos.py goes
    # - Get configured interfaces
    # - Determine which need LLDP config
    # - Enable LLDP, create profile, configure interfaces
    # - Commit, wait, query neighbors
    # - Restore and commit again


def _collect_ha_config(address, api_key, session):
    """Collect HA configuration and status.

    :param address: Management IP or hostname
    :param api_key: API key
    :param session: requests.Session
    :returns: dict with HA info (enabled, state, peer_serial, mode, etc.)
             Returns {'enabled': False} if HA is not configured
    """
    # TODO: Implement
    # - Execute: <show><high-availability>all</high-availability></show>
    # - Parse response
    # - Return HA configuration dict


def _create_ports_from_lldp(task, lldp_neighbors):
    """Create or update Ironic Port objects from LLDP neighbor data.

    :param task: TaskManager instance
    :param lldp_neighbors: list of LLDP neighbor dicts
    """
    # TODO: Implement
    # For each LLDP neighbor:
    # - Create port_name as "node_name:interface_name"
    # - Check if port already exists
    # - Create or update port with:
    #   - address (MAC)
    #   - local_link_connection (switch_id, switch_info, port_id)
    #   - extra (bios_name = remote interface)
    #   - physical_network (from node or default)
