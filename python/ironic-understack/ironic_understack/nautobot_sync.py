"""Ironic inspection hook to sync device information to Nautobot."""

import pynautobot
from ironic import objects
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)


class NautobotSyncHook(base.InspectionHook):
    """Hook to sync discovered device information to Nautobot."""

    # Run after port information has been enriched with BIOS names and LLDP data
    dependencies = ["update-baremetal-port", "port-bios-name"]

    def __call__(self, task, inventory, plugin_data):
        """Sync device inventory to Nautobot.

        :param task: Ironic task context containing node and driver info
        :param inventory: Hardware inventory dict from inspection
        :param plugin_data: Shared data dict between hooks
        """
        try:
            nautobot_url = CONF.ironic_understack.nautobot_url
            nautobot_token = CONF.ironic_understack.nautobot_token

            if not nautobot_url or not nautobot_token:
                LOG.warning(
                    "Nautobot URL or token not configured, skipping sync for node %s",
                    task.node.uuid,
                )
                return

            # Initialize Nautobot client
            nautobot = pynautobot.api(url=nautobot_url, token=nautobot_token)

            # Extract device information from inventory
            device_data = self._extract_device_data(task, inventory)

            # Sync to Nautobot
            self._sync_to_nautobot(nautobot, device_data, task.node)

            LOG.info(
                "Successfully synced device information to Nautobot for node %s",
                task.node.uuid,
            )

        except (KeyError, ValueError, TypeError) as e:
            msg = (
                f"Failed to extract device information from inventory for node "
                f"{task.node.uuid}: {e}"
            )
            LOG.error(msg)
            # Don't fail inspection, just log the error
        except Exception as e:
            msg = f"Failed to sync device to Nautobot for node {task.node.uuid}: {e}"
            LOG.error(msg)
            # Don't fail inspection, just log the error

    def _extract_device_data(self, task, inventory):
        """Extract relevant device data from inventory and baremetal ports."""
        # Use task.node properties directly - this is the source of truth
        data = {
            "uuid": task.node.uuid,
            "name": task.node.name,
            "properties": task.node.properties,
            "driver_info": task.node.driver_info,
        }

        # Extract interface information from baremetal ports
        # These ports have been enriched by
        # update-baremetal-port and port-bios-name hooks
        interfaces = []
        try:
            ports = objects.Port.list_by_node_id(task.context, task.node.id)
            for port in ports:
                interface_data = {
                    "mac_address": port.address,
                    "name": port.name,
                    "bios_name": port.extra.get("bios_name"),
                    "pxe_enabled": port.pxe_enabled,
                }

                # local_link_connection info from update-baremetal-port hook
                if port.local_link_connection:
                    interface_data["switch_id"] = port.local_link_connection.get(
                        "switch_id"
                    )
                    interface_data["switch_info"] = port.local_link_connection.get(
                        "switch_info"
                    )
                    interface_data["port_id"] = port.local_link_connection.get(
                        "port_id"
                    )

                # Add physical_network (VLAN group) if available
                if port.physical_network:
                    interface_data["physical_network"] = port.physical_network

                interfaces.append(interface_data)

            LOG.debug(
                "Extracted %d interfaces for node %s", len(interfaces), task.node.uuid
            )
        except Exception as e:
            LOG.warning(
                "Failed to extract interface data from ports for node %s: %s",
                task.node.uuid,
                e,
            )

        data["interfaces"] = interfaces

        return data

    def _sync_to_nautobot(self, nautobot, device_data, node):
        """Sync device data to Nautobot."""
        node_uuid = device_data.get("uuid")
        if not node_uuid:
            LOG.warning("Node has no UUID, cannot sync to Nautobot")
            return

        # Find device in Nautobot by UUID (Nautobot device ID = Ironic node UUID)
        device = self._find_device(nautobot, node_uuid)

        if not device:
            LOG.warning(
                "Device with UUID %s not found in Nautobot. "
                "Device must be pre-created in Nautobot before inspection.",
                node_uuid,
            )
            return

        LOG.info("Found device %s in Nautobot, syncing interfaces", node_uuid)

        # Sync interfaces to Nautobot
        self._sync_interfaces(nautobot, device, device_data)

    def _find_device(self, nautobot, device_uuid):
        """Find device in Nautobot by UUID.

        In Nautobot, the device ID is the same as the Ironic node UUID.
        """
        try:
            device = nautobot.dcim.devices.get(device_uuid)
            if device:
                LOG.info("Found device %s (%s) in Nautobot", device.name, device.id)
                return device
        except Exception:
            LOG.exception(
                "Error querying Nautobot for device with UUID %s", device_uuid
            )
        return None

    def _sync_interfaces(self, nautobot, device, device_data):
        """Sync interface information to Nautobot."""
        for interface_data in device_data.get("interfaces", []):
            try:
                self._sync_interface(nautobot, device, interface_data)
            except Exception as e:
                LOG.error(
                    "Failed to sync interface %s for device %s: %s",
                    interface_data.get("mac_address"),
                    device_data.get("uuid"),
                    e,
                )

    def _sync_interface(self, nautobot, device, interface_data):
        """Sync a single interface to Nautobot."""
        mac_address = interface_data.get("mac_address")
        if not mac_address:
            LOG.warning("Interface missing MAC address, skipping")
            return

        bios_name = interface_data.get("bios_name")
        if not bios_name:
            LOG.debug("Interface %s has no BIOS name, skipping", mac_address)
            return

        # Find or create the interface in Nautobot
        nautobot_interface = self._find_or_create_interface(
            nautobot, device, interface_data
        )

        # Connect interface to switch if we have LLDP data
        if interface_data.get("switch_id") and interface_data.get("port_id"):
            self._connect_interface_to_switch(
                nautobot, nautobot_interface, interface_data
            )

    def _find_or_create_interface(self, nautobot, device, interface_data):
        """Find or create an interface in Nautobot."""
        bios_name = interface_data["bios_name"]
        mac_address = interface_data["mac_address"]

        # Try to find existing interface by device and name
        try:
            interface = nautobot.dcim.interfaces.get(
                device_id=device.id, name=bios_name
            )
            if interface:
                LOG.info(
                    "Found existing interface %s (%s) in Nautobot",
                    bios_name,
                    interface.id,
                )
                # Update interface attributes
                interface.update(
                    mac_address=mac_address,
                    status="Active",
                    type="25gbase-x-sfp28",  # Default type, could be made configurable
                )
                return interface
        except Exception as e:
            LOG.debug("Interface lookup failed: %s", e)

        # Create new interface
        try:
            interface = nautobot.dcim.interfaces.create(
                device=device.id,
                name=bios_name,
                mac_address=mac_address,
                status="Active",
                type="25gbase-x-sfp28",
            )
            LOG.info("Created interface %s (%s) in Nautobot", bios_name, interface.id)
            return interface
        except Exception as e:
            LOG.error("Failed to create interface %s: %s", bios_name, e)
            raise

    def _connect_interface_to_switch(self, nautobot, server_interface, interface_data):
        """Connect server interface to switch interface via cable in Nautobot."""
        switch_chassis_id = interface_data.get("switch_id")
        switch_port_id = interface_data.get("port_id")

        if not all([switch_chassis_id, switch_port_id]):
            LOG.debug("Missing switch connection data for interface")
            return

        # Find the switch device by chassis MAC address
        switch = self._find_switch_by_mac(nautobot, switch_chassis_id)
        if not switch:
            LOG.warning(
                "Switch with chassis MAC %s not found in Nautobot, cannot create cable",
                switch_chassis_id,
            )
            return

        # Find the switch interface
        switch_interface = self._find_switch_interface(nautobot, switch, switch_port_id)
        if not switch_interface:
            LOG.warning(
                "Switch %s has no interface %s, cannot create cable",
                switch.name if hasattr(switch, "name") else switch.id,
                switch_port_id,
            )
            return

        # Create or verify cable connection
        self._create_or_verify_cable(nautobot, server_interface, switch_interface)

    def _find_switch_by_mac(self, nautobot, chassis_mac):
        """Find switch device by chassis MAC address."""
        try:
            # Nautobot stores chassis MAC in a custom field
            devices = nautobot.dcim.devices.filter(cf_chassis_mac_address=chassis_mac)
            if devices:
                return devices[0]
        except Exception as e:
            LOG.debug("Switch lookup by MAC failed: %s", e)
        return None

    def _find_switch_interface(self, nautobot, switch, port_name):
        """Find switch interface by port name."""
        try:
            interface = nautobot.dcim.interfaces.get(
                device_id=switch.id, name=port_name
            )
            return interface
        except Exception as e:
            LOG.debug("Switch interface lookup failed: %s", e)
        return None

    def _create_or_verify_cable(self, nautobot, server_interface, switch_interface):
        """Create or verify cable connection between server and switch."""
        try:
            # Check if cable already exists
            cable = nautobot.dcim.cables.get(
                termination_a_id=switch_interface.id,
                termination_b_id=server_interface.id,
            )
            if cable:
                LOG.info("Cable %s already exists in Nautobot", cable.id)
                return cable

            # Create new cable
            cable = nautobot.dcim.cables.create(
                termination_a_type="dcim.interface",
                termination_a_id=switch_interface.id,
                termination_b_type="dcim.interface",
                termination_b_id=server_interface.id,
                status="Connected",
            )
            LOG.info("Created cable %s in Nautobot", cable.id)
            return cable
        except Exception as e:
            LOG.error(
                "Failed to create cable between %s and %s: %s",
                server_interface.id,
                switch_interface.id,
                e,
            )
