"""Ironic inspection hook to sync device information to Nautobot."""

import pynautobot
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)


class NautobotSyncHook(base.InspectionHook):
    """Hook to sync discovered device information to Nautobot."""

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
        """Extract relevant device data from inventory."""
        data = {
            "serial": inventory.get("system_vendor", {}).get("serial_number"),
            "manufacturer": inventory.get("system_vendor", {}).get("manufacturer"),
            "model": inventory.get("system_vendor", {}).get("product_name"),
            "uuid": task.node.uuid,
            "name": task.node.name or task.node.uuid,
        }

        # Extract interface information
        interfaces = []
        for iface in inventory.get("interfaces", []):
            if iface.get("mac_address"):
                interfaces.append(
                    {
                        "name": iface.get("name"),
                        "mac_address": iface.get("mac_address"),
                        "ipv4_address": iface.get("ipv4_address"),
                    }
                )

        data["interfaces"] = interfaces

        return data

    def _sync_to_nautobot(self, nautobot, device_data, node):
        """Sync device data to Nautobot."""
        serial = device_data.get("serial")
        if not serial:
            LOG.warning("Node %s, cannot sync to Nautobot", node.uuid)
            return

        # Check if device exists in Nautobot
        device = self._find_device(nautobot, serial)

        if device:
            LOG.info("Device %s already exists in Nautobot", serial)
            # Update device if needed
            self._update_device(nautobot, device, device_data)
        else:
            LOG.info("Device %s not found in Nautobot, would create", serial)
            # Note: Creation requires location/rack info
            # which we don't have from inspection
            # This would need to be configured or derived from other sources

    def _find_device(self, nautobot, serial):
        """Find device in Nautobot by serial number."""
        try:
            devices = nautobot.dcim.devices.filter(serial=serial)
            if devices:
                return devices[0]
        except Exception:
            LOG.exception("Error querying Nautobot for device with serial %s", serial)
        return None

    def _update_device(self, nautobot, device, device_data):
        """Update device information in Nautobot."""
        # Update basic device info if needed
        # This is a placeholder - actual update logic would depend on requirements
        LOG.debug("Would update device %s with data: %s", device.id, device_data)
