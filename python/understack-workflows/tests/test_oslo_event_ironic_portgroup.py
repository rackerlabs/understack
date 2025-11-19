"""Tests for ironic_portgroup_event functionality."""

import json
from unittest.mock import Mock

import pytest

from understack_workflows.oslo_event.ironic_portgroup import IronicPortgroupEvent
from understack_workflows.oslo_event.ironic_portgroup import (
    handle_portgroup_create_update,
)
from understack_workflows.oslo_event.ironic_portgroup import handle_portgroup_delete


@pytest.fixture
def portgroup_create_event_data():
    """Load portgroup create event data from JSON sample."""
    with open("tests/json_samples/baremetal-portgroup-create-end.json") as f:
        raw_data = f.read()

    oslo_message = json.loads(raw_data)
    return json.loads(oslo_message["oslo.message"])


@pytest.fixture
def portgroup_update_event_data():
    """Load portgroup update event data from JSON sample."""
    with open("tests/json_samples/baremetal-portgroup-update-end.json") as f:
        raw_data = f.read()

    oslo_message = json.loads(raw_data)
    return json.loads(oslo_message["oslo.message"])


@pytest.fixture
def portgroup_delete_event_data():
    """Load portgroup delete event data from JSON sample."""
    with open("tests/json_samples/baremetal-portgroup-delete-end.json") as f:
        raw_data = f.read()

    oslo_message = json.loads(raw_data)
    return json.loads(oslo_message["oslo.message"])


class TestIronicPortgroupEvent:
    """Test IronicPortgroupEvent class."""

    def test_from_event_dict_create(self, portgroup_create_event_data):
        """Test parsing of portgroup create event data."""
        event = IronicPortgroupEvent.from_event_dict(portgroup_create_event_data)

        assert event.uuid == "629b8821-6c0a-4a6f-9312-109fe8a0931f"
        assert event.name == "bond0"
        assert event.node_uuid == "7ca98881-bca5-4c82-9369-66eb36292a95"
        assert event.address == "52:54:00:aa:bb:cc"
        assert event.mode == "active-backup"
        assert event.standalone_ports_supported is True
        assert event.properties == {}

    def test_from_event_dict_update(self, portgroup_update_event_data):
        """Test parsing of portgroup update event data."""
        event = IronicPortgroupEvent.from_event_dict(portgroup_update_event_data)

        assert event.uuid == "629b8821-6c0a-4a6f-9312-109fe8a0931f"
        assert event.name == "server-123_bond0"
        assert event.node_uuid == "7ca98881-bca5-4c82-9369-66eb36292a95"
        assert event.address == "52:54:00:aa:bb:cc"
        assert event.mode == "802.3ad"

    def test_from_event_dict_delete(self, portgroup_delete_event_data):
        """Test parsing of portgroup delete event data."""
        event = IronicPortgroupEvent.from_event_dict(portgroup_delete_event_data)

        assert event.uuid == "629b8821-6c0a-4a6f-9312-109fe8a0931f"
        assert event.name == "server-123_bond0"
        assert event.node_uuid == "7ca98881-bca5-4c82-9369-66eb36292a95"

    def test_lag_name_with_underscore(self):
        """Test LAG name extraction with underscore separator."""
        event = IronicPortgroupEvent(
            uuid="test-uuid",
            name="server-123_bond0",
            node_uuid="node-uuid",
            address="aa:bb:cc:dd:ee:ff",
            mode="802.3ad",
            properties={},
            standalone_ports_supported=True,
        )
        assert event.lag_name == "bond0"

    def test_lag_name_without_underscore(self):
        """Test LAG name when no underscore separator (returns as-is with warning)."""
        event = IronicPortgroupEvent(
            uuid="test-uuid",
            name="bond0",
            node_uuid="node-uuid",
            address="aa:bb:cc:dd:ee:ff",
            mode="802.3ad",
            properties={},
            standalone_ports_supported=True,
        )
        # Should return as-is when no underscore
        assert event.lag_name == "bond0"

    def test_lag_name_complex_interface_name(self):
        """Test LAG name extraction with complex interface name."""
        event = IronicPortgroupEvent(
            uuid="test-uuid",
            name="node-456_port-channel101",
            node_uuid="node-uuid",
            address="aa:bb:cc:dd:ee:ff",
            mode="802.3ad",
            properties={},
            standalone_ports_supported=True,
        )
        assert event.lag_name == "port-channel101"

    def test_lag_name_fallback_to_uuid(self):
        """Test LAG name fallback to UUID when name is None."""
        event = IronicPortgroupEvent(
            uuid="test-uuid-123",
            name=None,
            node_uuid="node-uuid",
            address="aa:bb:cc:dd:ee:ff",
            mode="802.3ad",
            properties={},
            standalone_ports_supported=True,
        )
        assert event.lag_name == "test-uuid-123"


class TestHandlePortgroupCreateUpdate:
    """Test handle_portgroup_create_update function."""

    @pytest.fixture
    def mock_conn(self):
        """Create mock connection."""
        return Mock()

    @pytest.fixture
    def mock_nautobot(self):
        """Create mock nautobot instance."""
        nautobot = Mock()
        return nautobot

    def test_create_portgroup(
        self, mock_conn, mock_nautobot, portgroup_create_event_data
    ):
        """Test creating portgroup syncs to Nautobot only."""
        # Mock no existing LAG interface
        mock_nautobot.dcim.interfaces.get.return_value = None

        # Mock LAG interface creation
        created_lag = Mock()
        created_lag.id = "629b8821-6c0a-4a6f-9312-109fe8a0931f"
        mock_nautobot.dcim.interfaces.create.return_value = created_lag

        # Test the function
        result = handle_portgroup_create_update(
            mock_conn, mock_nautobot, portgroup_create_event_data
        )

        # Verify result
        assert result == 0

        # Verify NO Ironic updates were made (inspection hook handles that)
        assert (
            not hasattr(mock_conn.baremetal, "update_port_group")
            or not mock_conn.baremetal.update_port_group.called
        )

        # Verify LAG interface was created in Nautobot
        mock_nautobot.dcim.interfaces.create.assert_called_once()
        call_args = mock_nautobot.dcim.interfaces.create.call_args[1]
        assert call_args["id"] == "629b8821-6c0a-4a6f-9312-109fe8a0931f"
        assert call_args["name"] == "bond0"  # Stripped name
        assert call_args["device"] == "7ca98881-bca5-4c82-9369-66eb36292a95"
        assert call_args["type"] == "lag"
        assert call_args["status"] == "Active"
        assert call_args["mac_address"] == "52:54:00:aa:bb:cc"
        assert call_args["description"] == "Bond mode: active-backup"

    def test_update_portgroup(
        self, mock_conn, mock_nautobot, portgroup_update_event_data
    ):
        """Test updating portgroup syncs to Nautobot only."""
        # Mock existing LAG interface
        existing_lag = Mock()
        existing_lag.id = "629b8821-6c0a-4a6f-9312-109fe8a0931f"
        mock_nautobot.dcim.interfaces.get.return_value = existing_lag

        # Test the function
        result = handle_portgroup_create_update(
            mock_conn, mock_nautobot, portgroup_update_event_data
        )

        # Verify result
        assert result == 0

        # Verify NO Ironic updates were made (inspection hook handles that)
        assert (
            not hasattr(mock_conn.baremetal, "update_port_group")
            or not mock_conn.baremetal.update_port_group.called
        )

        # Verify LAG interface was updated in Nautobot
        existing_lag.save.assert_called_once()
        assert existing_lag.name == "bond0"  # Stripped name
        assert existing_lag.status == "Active"
        assert existing_lag.type == "lag"
        assert existing_lag.description == "Bond mode: 802.3ad"

    def test_create_portgroup_nautobot_error(
        self, mock_conn, mock_nautobot, portgroup_create_event_data
    ):
        """Test creating portgroup when Nautobot creation fails."""
        # Mock no existing LAG interface
        mock_nautobot.dcim.interfaces.get.return_value = None

        # Mock LAG interface creation failure
        mock_nautobot.dcim.interfaces.create.side_effect = Exception(
            "Nautobot API error"
        )

        # Test the function
        result = handle_portgroup_create_update(
            mock_conn, mock_nautobot, portgroup_create_event_data
        )

        # Verify error result
        assert result == 1

    def test_create_portgroup_without_mac_address(self, mock_conn, mock_nautobot):
        """Test creating portgroup without MAC address."""
        # Create event data without MAC address
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "uuid": "test-uuid",
                    "name": "bond0",
                    "node_uuid": "node-uuid",
                    "address": None,  # No MAC address
                    "mode": "802.3ad",
                    "properties": {},
                    "standalone_ports_supported": True,
                }
            }
        }

        # Mock no existing LAG interface
        mock_nautobot.dcim.interfaces.get.return_value = None

        # Mock LAG interface creation
        created_lag = Mock()
        mock_nautobot.dcim.interfaces.create.return_value = created_lag

        # Test the function
        result = handle_portgroup_create_update(mock_conn, mock_nautobot, event_data)

        # Verify result
        assert result == 0

        # Verify LAG interface was created without MAC address
        call_args = mock_nautobot.dcim.interfaces.create.call_args[1]
        assert "mac_address" not in call_args

    def test_create_portgroup_race_condition(
        self, mock_conn, mock_nautobot, portgroup_create_event_data
    ):
        """Test handling race condition when interface is created by another process."""
        import pynautobot.core.query

        # Mock no existing LAG interface initially (both lookups return None)
        existing_lag = Mock()
        existing_lag.id = "629b8821-6c0a-4a6f-9312-109fe8a0931f"

        # First get() call returns None (by UUID)
        # Second get() (after race condition) returns the interface
        mock_nautobot.dcim.interfaces.get.side_effect = [None, existing_lag]

        # Mock create() raising duplicate error (race condition)
        mock_request = Mock()
        mock_request.status_code = 400
        mock_request.text = "The fields device, name must make a unique set."
        mock_request.json.return_value = {
            "non_field_errors": ["The fields device, name must make a unique set."]
        }

        # Create RequestError with proper structure
        error = pynautobot.core.query.RequestError(mock_request)
        error.req = mock_request  # RequestError expects req attribute
        # Make str(error) contain "unique set"
        error.error = "The fields device, name must make a unique set."

        mock_nautobot.dcim.interfaces.create.side_effect = error

        # Test the function
        result = handle_portgroup_create_update(
            mock_conn, mock_nautobot, portgroup_create_event_data
        )

        # Verify result is success (race condition handled)
        assert result == 0

        # Verify create was attempted
        assert mock_nautobot.dcim.interfaces.create.call_count == 1

        # Verify get was called twice (initial lookup + after race)
        assert mock_nautobot.dcim.interfaces.get.call_count == 2

        # Verify the existing interface was updated
        existing_lag.save.assert_called_once()


class TestHandlePortgroupDelete:
    """Test handle_portgroup_delete function."""

    @pytest.fixture
    def mock_conn(self):
        """Create mock connection."""
        return Mock()

    @pytest.fixture
    def mock_nautobot(self):
        """Create mock nautobot instance."""
        nautobot = Mock()
        return nautobot

    def test_delete_portgroup_success(
        self, mock_conn, mock_nautobot, portgroup_delete_event_data
    ):
        """Test successful portgroup deletion."""
        # Mock existing LAG interface
        existing_lag = Mock()
        existing_lag.id = "629b8821-6c0a-4a6f-9312-109fe8a0931f"
        mock_nautobot.dcim.interfaces.get.return_value = existing_lag

        # Test the function
        result = handle_portgroup_delete(
            mock_conn, mock_nautobot, portgroup_delete_event_data
        )

        # Verify result
        assert result == 0

        # Verify LAG interface was deleted
        existing_lag.delete.assert_called_once()

    def test_delete_portgroup_not_found(
        self, mock_conn, mock_nautobot, portgroup_delete_event_data
    ):
        """Test deleting portgroup when LAG interface not found."""
        # Mock LAG interface not found
        mock_nautobot.dcim.interfaces.get.return_value = None

        # Test the function
        result = handle_portgroup_delete(
            mock_conn, mock_nautobot, portgroup_delete_event_data
        )

        # Verify result (success - nothing to delete)
        assert result == 0

    def test_delete_portgroup_nautobot_error(
        self, mock_conn, mock_nautobot, portgroup_delete_event_data
    ):
        """Test deleting portgroup when Nautobot deletion fails."""
        # Mock existing LAG interface
        existing_lag = Mock()
        existing_lag.delete.side_effect = Exception("Nautobot API error")
        mock_nautobot.dcim.interfaces.get.return_value = existing_lag

        # Test the function
        result = handle_portgroup_delete(
            mock_conn, mock_nautobot, portgroup_delete_event_data
        )

        # Verify error result
        assert result == 1
