"""Tests for nautobot_sync inspection hook."""

import unittest
from unittest import mock

from ironic import objects

from ironic_understack.nautobot_sync import NautobotSyncHook

# Register all Ironic objects
objects.register_all()


class TestNautobotSyncHook(unittest.TestCase):
    """Test NautobotSyncHook inspection hook."""

    def setUp(self):
        """Set up test fixtures."""
        self.hook = NautobotSyncHook()
        self.task = mock.Mock()
        self.task.node = mock.Mock()
        self.task.node.uuid = "test-node-uuid"
        self.task.node.name = "test-node-name"
        self.task.node.id = 123
        self.task.node.properties = {}
        self.task.node.driver_info = {}
        self.task.context = mock.Mock()

    @mock.patch("ironic_understack.nautobot_sync.CONF")
    def test_missing_nautobot_url(self, mock_conf):
        """Test hook skips sync when Nautobot URL is not configured."""
        mock_conf.ironic_understack.nautobot_url = None
        mock_conf.ironic_understack.nautobot_token = "test-token"

        inventory = {}
        plugin_data = {}

        # Should not raise exception, just log warning
        self.hook(self.task, inventory, plugin_data)

    @mock.patch("ironic_understack.nautobot_sync.CONF")
    def test_missing_nautobot_token(self, mock_conf):
        """Test hook skips sync when Nautobot token is not configured."""
        mock_conf.ironic_understack.nautobot_url = "http://nautobot.example.com"
        mock_conf.ironic_understack.nautobot_token = None

        inventory = {}
        plugin_data = {}

        # Should not raise exception, just log warning
        self.hook(self.task, inventory, plugin_data)

    @mock.patch("ironic_understack.nautobot_sync.pynautobot")
    @mock.patch("ironic_understack.nautobot_sync.CONF")
    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_device_not_found_in_nautobot(
        self, mock_list_ports, mock_conf, mock_pynautobot
    ):
        """Test hook handles device not found in Nautobot."""
        mock_conf.ironic_understack.nautobot_url = "http://nautobot.example.com"
        mock_conf.ironic_understack.nautobot_token = "test-token"

        inventory = {}
        plugin_data = {}

        mock_list_ports.return_value = []

        # Mock Nautobot API - device not found
        mock_nautobot_instance = mock.Mock()
        mock_pynautobot.api.return_value = mock_nautobot_instance
        mock_nautobot_instance.dcim.devices.get.return_value = None

        self.hook(self.task, inventory, plugin_data)

        # Verify device lookup was attempted by UUID
        mock_nautobot_instance.dcim.devices.get.assert_called_once_with(
            "test-node-uuid"
        )

    @mock.patch("ironic_understack.nautobot_sync.pynautobot")
    @mock.patch("ironic_understack.nautobot_sync.CONF")
    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_device_found_in_nautobot(
        self, mock_list_ports, mock_conf, mock_pynautobot
    ):
        """Test hook handles device already existing in Nautobot."""
        mock_conf.ironic_understack.nautobot_url = "http://nautobot.example.com"
        mock_conf.ironic_understack.nautobot_token = "test-token"

        inventory = {}
        plugin_data = {}

        mock_list_ports.return_value = []

        # Mock Nautobot API - device found
        mock_device = mock.Mock()
        mock_device.id = "test-node-uuid"
        mock_device.name = "Dell-ABC123"
        mock_nautobot_instance = mock.Mock()
        mock_pynautobot.api.return_value = mock_nautobot_instance
        mock_nautobot_instance.dcim.devices.get.return_value = mock_device

        self.hook(self.task, inventory, plugin_data)

        # Verify device lookup was attempted
        mock_nautobot_instance.dcim.devices.get.assert_called_once_with(
            "test-node-uuid"
        )

    @mock.patch("ironic_understack.nautobot_sync.pynautobot")
    @mock.patch("ironic_understack.nautobot_sync.CONF")
    def test_nautobot_api_exception(self, mock_conf, mock_pynautobot):
        """Test hook handles Nautobot API exceptions gracefully."""
        mock_conf.ironic_understack.nautobot_url = "http://nautobot.example.com"
        mock_conf.ironic_understack.nautobot_token = "test-token"

        inventory = {}
        plugin_data = {}

        # Mock Nautobot API to raise exception
        mock_pynautobot.api.side_effect = Exception("Connection error")

        # Should not raise exception, just log error
        self.hook(self.task, inventory, plugin_data)

    @mock.patch("ironic_understack.nautobot_sync.pynautobot")
    @mock.patch("ironic_understack.nautobot_sync.CONF")
    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_empty_inventory(self, mock_list_ports, mock_conf, mock_pynautobot):
        """Test hook handles empty inventory gracefully."""
        mock_conf.ironic_understack.nautobot_url = "http://nautobot.example.com"
        mock_conf.ironic_understack.nautobot_token = "test-token"

        inventory = {}
        plugin_data = {}

        mock_list_ports.return_value = []

        # Mock Nautobot API
        mock_nautobot_instance = mock.Mock()
        mock_pynautobot.api.return_value = mock_nautobot_instance
        mock_nautobot_instance.dcim.devices.get.return_value = None

        # Should not raise exception
        self.hook(self.task, inventory, plugin_data)

    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_extract_device_data_method(self, mock_list_ports):
        """Test _extract_device_data method directly."""
        inventory = {}

        # Mock a port
        port = mock.Mock()
        port.address = "00:11:22:33:44:55"
        port.name = "eth0"
        port.pxe_enabled = True
        port.extra = {"bios_name": "NIC.Slot.1-1"}
        port.local_link_connection = {}
        port.physical_network = None
        mock_list_ports.return_value = [port]

        data = self.hook._extract_device_data(self.task, inventory)

        assert data["uuid"] == "test-node-uuid"
        assert data["name"] == "test-node-name"
        assert len(data["interfaces"]) == 1
        assert data["interfaces"][0]["name"] == "eth0"
        assert data["interfaces"][0]["mac_address"] == "00:11:22:33:44:55"
        assert data["interfaces"][0]["bios_name"] == "NIC.Slot.1-1"

    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_extract_device_data_missing_fields(self, mock_list_ports):
        """Test _extract_device_data handles missing fields."""
        inventory = {}
        mock_list_ports.return_value = []

        data = self.hook._extract_device_data(self.task, inventory)

        assert data["uuid"] == "test-node-uuid"
        assert data["interfaces"] == []

    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_extract_enriched_port_data(self, mock_list_ports):
        """Test _extract_device_data extracts enriched port information."""
        inventory = {}

        # Mock enriched port with LLDP and BIOS name data
        port = mock.Mock()
        port.address = "14:23:f3:f5:3c:90"
        port.name = "1423f3f53c90"
        port.pxe_enabled = True
        port.extra = {"bios_name": "NIC.Slot.1-1"}
        port.local_link_connection = {
            "switch_id": "c4:7e:e0:e4:03:37",
            "switch_info": "f20-3-2.iad3",
            "port_id": "Ethernet1/1",
        }
        port.physical_network = "datacenter1-network"

        mock_list_ports.return_value = [port]

        data = self.hook._extract_device_data(self.task, inventory)

        assert len(data["interfaces"]) == 1
        iface = data["interfaces"][0]
        assert iface["mac_address"] == "14:23:f3:f5:3c:90"
        assert iface["name"] == "1423f3f53c90"
        assert iface["bios_name"] == "NIC.Slot.1-1"
        assert iface["pxe_enabled"] is True
        assert iface["switch_id"] == "c4:7e:e0:e4:03:37"
        assert iface["switch_info"] == "f20-3-2.iad3"
        assert iface["port_id"] == "Ethernet1/1"
        assert iface["physical_network"] == "datacenter1-network"

    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_extract_port_without_lldp_data(self, mock_list_ports):
        """Test _extract_device_data handles ports without LLDP data."""
        inventory = {}

        # Mock port without LLDP data
        port = mock.Mock()
        port.address = "00:11:22:33:44:55"
        port.name = "00112233445"
        port.pxe_enabled = False
        port.extra = {}
        port.local_link_connection = {}
        port.physical_network = None

        mock_list_ports.return_value = [port]

        data = self.hook._extract_device_data(self.task, inventory)

        assert len(data["interfaces"]) == 1
        iface = data["interfaces"][0]
        assert iface["mac_address"] == "00:11:22:33:44:55"
        assert iface["bios_name"] is None
        assert "switch_id" not in iface or iface.get("switch_id") is None
        assert "physical_network" not in iface

    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_extract_multiple_ports(self, mock_list_ports):
        """Test _extract_device_data handles multiple ports."""
        inventory = {}

        # Mock multiple ports
        port1 = mock.Mock()
        port1.address = "00:11:22:33:44:55"
        port1.name = "port1"
        port1.pxe_enabled = True
        port1.extra = {"bios_name": "NIC.Slot.1-1"}
        port1.local_link_connection = {}
        port1.physical_network = None

        port2 = mock.Mock()
        port2.address = "00:11:22:33:44:56"
        port2.name = "port2"
        port2.pxe_enabled = False
        port2.extra = {"bios_name": "NIC.Slot.1-2"}
        port2.local_link_connection = {}
        port2.physical_network = None

        mock_list_ports.return_value = [port1, port2]

        data = self.hook._extract_device_data(self.task, inventory)

        assert len(data["interfaces"]) == 2
        assert data["interfaces"][0]["mac_address"] == "00:11:22:33:44:55"
        assert data["interfaces"][1]["mac_address"] == "00:11:22:33:44:56"

    @mock.patch("ironic_understack.nautobot_sync.pynautobot")
    @mock.patch("ironic_understack.nautobot_sync.CONF")
    @mock.patch.object(objects.Port, "list_by_node_id")
    def test_sync_interface_with_lldp_data(
        self, mock_list_ports, mock_conf, mock_pynautobot
    ):
        """Test syncing interface with LLDP data creates cable."""
        mock_conf.ironic_understack.nautobot_url = "http://nautobot.example.com"
        mock_conf.ironic_understack.nautobot_token = "test-token"

        inventory = {}
        plugin_data = {}

        # Mock port with LLDP data
        port = mock.Mock()
        port.address = "14:23:f3:f5:3c:90"
        port.name = "1423f3f53c90"
        port.pxe_enabled = True
        port.extra = {"bios_name": "NIC.Slot.1-1"}
        port.local_link_connection = {
            "switch_id": "c4:7e:e0:e4:03:37",
            "switch_info": "f20-3-2.iad3",
            "port_id": "Ethernet1/1",
        }
        port.physical_network = "datacenter1-network"
        mock_list_ports.return_value = [port]

        # Mock Nautobot API
        mock_device = mock.Mock()
        mock_device.id = "test-node-uuid"
        mock_device.name = "Dell-ABC123"

        mock_interface = mock.Mock()
        mock_interface.id = "interface-123"
        mock_interface.update = mock.Mock()

        mock_switch = mock.Mock()
        mock_switch.id = "switch-123"
        mock_switch.name = "f20-3-2"

        mock_switch_interface = mock.Mock()
        mock_switch_interface.id = "switch-interface-123"

        mock_nautobot_instance = mock.Mock()
        mock_pynautobot.api.return_value = mock_nautobot_instance
        mock_nautobot_instance.dcim.devices.get.return_value = mock_device
        mock_nautobot_instance.dcim.interfaces.get.side_effect = [
            mock_interface,
            mock_switch_interface,
        ]
        mock_nautobot_instance.dcim.devices.filter.return_value = [mock_switch]
        mock_nautobot_instance.dcim.cables.get.return_value = None
        mock_nautobot_instance.dcim.cables.create.return_value = mock.Mock(
            id="cable-123"
        )

        self.hook(self.task, inventory, plugin_data)

        # Verify interface was found/created
        assert mock_nautobot_instance.dcim.interfaces.get.called
        # Verify cable was created
        assert mock_nautobot_instance.dcim.cables.create.called


if __name__ == "__main__":
    unittest.main()
