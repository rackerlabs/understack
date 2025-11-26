"""Tests for ironic_port_event functionality."""

import json
from unittest.mock import Mock

import pytest

from understack_workflows.oslo_event.ironic_port import IronicPortEvent
from understack_workflows.oslo_event.ironic_port import _handle_cable_management
from understack_workflows.oslo_event.ironic_port import handle_port_create_update
from understack_workflows.oslo_event.ironic_port import handle_port_delete


@pytest.fixture
def port_create_event_data():
    """Load port create event data from JSON sample."""
    with open("tests/json_samples/baremetal-port-create-end.json") as f:
        raw_data = f.read()

    oslo_message = json.loads(raw_data)
    return json.loads(oslo_message["oslo.message"])


@pytest.fixture
def port_update_event_data():
    """Load port update event data from JSON sample."""
    with open("tests/json_samples/baremetal-port-update-end.json") as f:
        raw_data = f.read()

    oslo_message = json.loads(raw_data)
    return json.loads(oslo_message["oslo.message"])


@pytest.fixture
def port_delete_event_data():
    """Load port delete event data from JSON sample."""
    with open("tests/json_samples/baremetal-port-delete-end.json") as f:
        raw_data = f.read()

    oslo_message = json.loads(raw_data)
    return json.loads(oslo_message["oslo.message"])


class TestIronicPortEvent:
    """Test IronicPortEvent class."""

    def test_from_event_dict_create(self, port_create_event_data):
        """Test parsing of port create event data."""
        event = IronicPortEvent.from_event_dict(port_create_event_data)

        assert event.uuid == "63a3c79c-dd84-4569-a398-cc795287300f"
        assert event.name == "1327172-hp1:NIC2-1"
        # interface_name now returns the port name directly (MAC address)
        assert event.interface_name == "1327172-hp1:NIC2-1"
        assert event.address == "00:11:0a:69:a9:99"
        assert event.node_uuid == "7ca98881-bca5-4c82-9369-66eb36292a95"
        assert event.physical_network == "f20-1-network"
        assert event.pxe_enabled is True
        assert event.remote_port_id == "Ethernet1/1"
        assert event.remote_switch_info == "f20-1-2.iad3.rackspace.net"
        assert event.remote_switch_id == "c4:7e:e0:e4:2e:2f"

    def test_from_event_dict_update(self, port_update_event_data):
        """Test parsing of port update event data."""
        event = IronicPortEvent.from_event_dict(port_update_event_data)

        assert event.uuid == "438711ba-1bcd-4f19-8b34-53cdc6d61bc4"
        assert event.name == "1327172-hp1:NIC1-1"
        # interface_name now returns the port name directly (MAC address)
        assert event.interface_name == "1327172-hp1:NIC1-1"
        assert event.address == "00:11:0a:6a:c7:05"
        assert event.node_uuid == "7ca98881-bca5-4c82-9369-66eb36292a95"
        assert event.remote_port_id == "Ethernet1/1"
        assert event.remote_switch_info == "f20-1-1.iad3.rackspace.net"
        assert event.remote_switch_id == "c4:7e:e0:e3:ec:2b"

    def test_from_event_dict_delete(self, port_delete_event_data):
        """Test parsing of port delete event data."""
        event = IronicPortEvent.from_event_dict(port_delete_event_data)

        assert event.uuid == "f8888f0b-1451-432e-9ae7-4b77303dd9ef"
        assert event.name == "f8888f0b-1451-432e-9ae7-4b77303dd9ef:NIC.Integrated.1-2"
        # interface_name now returns the port name directly (MAC address)
        assert (
            event.interface_name
            == "f8888f0b-1451-432e-9ae7-4b77303dd9ef:NIC.Integrated.1-2"
        )
        assert event.address == "d4:04:e6:4f:64:5d"
        assert event.node_uuid == "74feccaf-3aae-401c-bc1f-eeeb26b9f542"
        assert event.remote_port_id == "Ethernet1/14"
        assert event.remote_switch_info == "f20-5-1f.iad3.rackspace.net"
        assert event.remote_switch_id == "f4:ee:31:c0:8c:b3"

    def test_interface_name_with_mac_address(self):
        """Test interface name returns MAC address when set."""
        event = IronicPortEvent(
            uuid="test-uuid",
            name="00110a69a999",  # MAC address (normalized)
            address="00:11:0a:69:a9:99",
            node_uuid="node-uuid",
            physical_network="test-network",
            pxe_enabled=True,
            remote_port_id="Ethernet1/1",
            remote_switch_info="switch1.example.com",
            remote_switch_id="aa:bb:cc:dd:ee:ff",
        )
        assert event.interface_name == "00110a69a999"

    def test_interface_name_fallback_to_uuid(self):
        """Test interface name falls back to UUID when name is empty."""
        event = IronicPortEvent(
            uuid="test-uuid-123",
            name="",  # Empty name
            address="00:11:22:33:44:55",
            node_uuid="node-uuid",
            physical_network="test-network",
            pxe_enabled=True,
            remote_port_id="Ethernet1/1",
            remote_switch_info="switch1.example.com",
            remote_switch_id="aa:bb:cc:dd:ee:ff",
        )
        assert event.interface_name == "test-uuid-123"


class TestCableManagement:
    """Test cable management functionality."""

    @pytest.fixture
    def mock_nautobot(self):
        """Create mock nautobot instance."""
        nautobot = Mock()
        return nautobot

    @pytest.fixture
    def mock_server_interface(self):
        """Create mock server interface."""
        server_interface = Mock()
        server_interface.id = "server-interface-789"
        return server_interface

    @pytest.fixture
    def test_event(self):
        """Create test event."""
        return IronicPortEvent(
            uuid="test-uuid",
            name="test-name",
            address="00:11:22:33:44:55",
            node_uuid="node-uuid",
            physical_network="test-network",
            pxe_enabled=True,
            remote_port_id="Ethernet1/1",
            remote_switch_info="switch1.example.com",
            remote_switch_id="aa:bb:cc:dd:ee:ff",
        )

    def test_cable_management_create_new_cable(
        self, mock_nautobot, mock_server_interface, test_event
    ):
        """Test creating a new cable when none exists."""
        # Mock server interface has no existing cable
        mock_server_interface.cable = None

        # Mock switch interface lookup directly by device and name
        switch_interface = Mock()
        switch_interface.id = "switch-interface-456"
        mock_nautobot.dcim.interfaces.get.return_value = switch_interface

        # Mock cable creation
        created_cable = Mock()
        created_cable.id = "cable-999"
        mock_nautobot.dcim.cables.create.return_value = created_cable

        # Test cable management
        _handle_cable_management(mock_nautobot, mock_server_interface, test_event)

        # Verify switch interface lookup call
        mock_nautobot.dcim.interfaces.get.assert_called_with(
            device="switch1.example.com", name="Ethernet1/1"
        )
        # Verify cable creation was called
        mock_nautobot.dcim.cables.create.assert_called_with(
            termination_a_type="dcim.interface",
            termination_a_id="test-uuid",
            termination_b_type="dcim.interface",
            termination_b_id="switch-interface-456",
            status="Connected",
        )

    def test_cable_management_existing_correct_cable(
        self, mock_nautobot, mock_server_interface, test_event
    ):
        """Test when correct cable already exists."""
        # Mock existing cable with correct connection
        existing_cable = Mock()
        existing_cable.id = "cable-123"
        existing_cable.termination_b_type = "dcim.interface"
        existing_cable.termination_b_id = "switch-interface-456"
        mock_nautobot.dcim.cables.get.return_value = existing_cable

        # Test cable management
        _handle_cable_management(mock_nautobot, mock_server_interface, test_event)

        # Verify no cable creation was attempted
        mock_nautobot.dcim.cables.create.assert_not_called()
        existing_cable.save.assert_not_called()

    def test_cable_management_update_existing_cable(
        self, mock_nautobot, mock_server_interface, test_event
    ):
        """Test updating existing cable with wrong connection."""
        # Mock switch interface lookup
        switch_interface = Mock()
        switch_interface.id = "switch-interface-456"
        mock_nautobot.dcim.interfaces.get.return_value = switch_interface

        # Mock existing cable with wrong connection
        existing_cable = Mock()
        existing_cable.id = "cable-123"
        existing_cable.termination_a_id = "test-uuid"
        existing_cable.termination_b_id = "wrong-interface-123"  # Wrong connection
        mock_server_interface.cable = existing_cable

        # Test cable management
        _handle_cable_management(mock_nautobot, mock_server_interface, test_event)

        # Verify cable was updated
        assert existing_cable.termination_a_type == "dcim.interface"
        assert existing_cable.termination_a_id == "test-uuid"
        assert existing_cable.termination_b_type == "dcim.interface"
        assert existing_cable.termination_b_id == "switch-interface-456"
        assert existing_cable.status == "Connected"
        existing_cable.save.assert_called_once()
        mock_nautobot.dcim.cables.create.assert_not_called()

    def test_cable_management_switch_not_found(
        self, mock_nautobot, mock_server_interface, test_event
    ):
        """Test when switch interface is not found."""
        # Mock switch interface not found
        mock_nautobot.dcim.interfaces.get.return_value = None

        # Test cable management
        result = _handle_cable_management(
            mock_nautobot, mock_server_interface, test_event
        )

        # Verify switch interface lookup was attempted
        mock_nautobot.dcim.interfaces.get.assert_called_with(
            device="switch1.example.com", name="Ethernet1/1"
        )
        # Verify no cable operations were attempted
        mock_nautobot.dcim.cables.create.assert_not_called()
        # Verify error return code
        assert result == 1


class TestHandlePortCreateUpdate:
    """Test handle_port_create_update function."""

    @pytest.fixture
    def mock_nautobot(self):
        """Create mock nautobot instance."""
        nautobot = Mock()

        # Mock interface lookup
        interface = Mock()
        interface.id = "interface-123"
        nautobot.dcim.interfaces.get.return_value = interface

        return nautobot

    @pytest.fixture
    def mock_conn(self):
        """Create mock connection."""
        return Mock()

    def test_handle_port_create_update_with_remote_info(
        self, mock_conn, mock_nautobot, port_create_event_data
    ):
        """Test handling port create/update with remote connection info."""
        # Mock server interface creation
        created_interface = Mock()
        created_interface.id = "interface-456"
        created_interface.cable = None  # No existing cable
        mock_nautobot.dcim.interfaces.create.return_value = created_interface

        # Mock switch interface for cable management
        switch_interface = Mock()
        switch_interface.id = "switch-interface-456"

        # Mock the interface get calls
        def mock_interface_get(*args, **kwargs):
            if "id" in kwargs:
                # Server interface lookup by ID - not found
                return None
            elif "device" in kwargs and "name" in kwargs:
                if kwargs["device"] == "7ca98881-bca5-4c82-9369-66eb36292a95":
                    # Server interface lookup by device+name - not found
                    return None
                elif kwargs["device"] == "f20-1-2.iad3.rackspace.net":
                    # Switch interface lookup
                    return switch_interface
                else:
                    return None
            return None

        mock_nautobot.dcim.interfaces.get.side_effect = mock_interface_get

        # Mock cable creation
        created_cable = Mock()
        created_cable.id = "cable-999"
        mock_nautobot.dcim.cables.create.return_value = created_cable

        # Test the function
        result = handle_port_create_update(
            mock_conn, mock_nautobot, port_create_event_data
        )

        # Verify result
        assert result == 0

        # Verify interface creation was called
        mock_nautobot.dcim.interfaces.create.assert_called_once()

        # Verify cable creation was called
        mock_nautobot.dcim.cables.create.assert_called_once()


class TestHandlePortDelete:
    """Test handle_port_delete function."""

    @pytest.fixture
    def mock_nautobot(self):
        """Create mock nautobot instance."""
        nautobot = Mock()

        # Mock interface
        interface = Mock()
        interface.id = "interface-123"
        nautobot.dcim.interfaces.get.return_value = interface

        return nautobot

    @pytest.fixture
    def mock_conn(self):
        """Create mock connection."""
        return Mock()

    def test_handle_port_delete_with_cable(
        self, mock_conn, mock_nautobot, port_delete_event_data
    ):
        """Test handling port delete with existing cable."""
        # Mock existing cable
        existing_cable = Mock()
        existing_cable.id = "cable-123"
        mock_nautobot.dcim.cables.get.return_value = existing_cable

        # Test the function
        result = handle_port_delete(mock_conn, mock_nautobot, port_delete_event_data)

        # Verify result
        assert result == 0

        # Verify cable deletion was called
        existing_cable.delete.assert_called_once()

        # Verify interface deletion was called
        mock_nautobot.dcim.interfaces.get.return_value.delete.assert_called_once()

    def test_handle_port_delete_interface_not_found(
        self, mock_conn, mock_nautobot, port_delete_event_data
    ):
        """Test handling port delete when interface is not found."""
        # Mock interface not found
        mock_nautobot.dcim.interfaces.get.return_value = None

        # Test the function
        result = handle_port_delete(mock_conn, mock_nautobot, port_delete_event_data)

        # Verify result
        assert result == 0

        # Verify no cable operations were attempted
        mock_nautobot.dcim.cables.get.assert_not_called()
