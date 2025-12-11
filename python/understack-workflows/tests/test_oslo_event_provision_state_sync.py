"""Unit tests for provision_state_sync oslo event handler."""

import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.oslo_event.provision_state_sync import handle_provision_end


class TestHandleProvisionEnd:
    """Test cases for handle_provision_end function."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock OpenStack connection."""
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        """Create a mock Nautobot API instance."""
        mock = MagicMock()
        mock.base_url = "http://nautobot.example.com"
        mock.token = "test-token"
        return mock

    @pytest.fixture
    def valid_event_data(self):
        """Create valid event data for testing."""
        node_uuid = uuid.uuid4()
        lessee_uuid = uuid.uuid4()
        return {
            "payload": {
                "ironic_object.data": {
                    "uuid": str(node_uuid),
                    "provision_state": "active",
                    "lessee": str(lessee_uuid),
                    "resource_class": "baremetal",
                }
            }
        }

    @pytest.fixture
    def minimal_event_data(self):
        """Create minimal valid event data (only required fields)."""
        node_uuid = uuid.uuid4()
        return {
            "payload": {
                "ironic_object.data": {
                    "uuid": str(node_uuid),
                    "provision_state": "available",
                }
            }
        }

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_success_with_all_fields(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test successful handling with all fields present."""
        # Setup mocks
        mock_mapper.translate_to_nautobot.return_value = "Active"
        mock_nb_helper = MagicMock()
        mock_nb_helper_class.return_value = mock_nb_helper

        # Execute
        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        # Verify
        assert result == 0

        # Check mapper was called
        mock_mapper.translate_to_nautobot.assert_called_once_with("active")

        # Check NautobotHelper was initialized correctly
        mock_nb_helper_class.assert_called_once_with(
            url="http://nautobot.example.com",
            token="test-token",
            logger=mock_nb_helper_class.call_args[1]["logger"],
            session=mock_nautobot,
        )

        # Check update_cf was called with correct parameters
        ironic_data = valid_event_data["payload"]["ironic_object.data"]
        expected_device_uuid = uuid.UUID(ironic_data["uuid"])
        expected_tenant_uuid = uuid.UUID(ironic_data["lessee"])

        mock_nb_helper.update_cf.assert_called_once_with(
            device_id=expected_device_uuid,
            tenant_id=expected_tenant_uuid,
            fields={
                "ironic_provision_state": "active",
                "resource_class": "baremetal",
            },
        )

        # Check update_device_status was called
        mock_nb_helper.update_device_status.assert_called_once_with(
            expected_device_uuid, "Active"
        )

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_success_minimal_fields(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
        minimal_event_data,
    ):
        """Test successful handling with only required fields."""
        # Setup mocks
        mock_mapper.translate_to_nautobot.return_value = "Planned"
        mock_nb_helper = MagicMock()
        mock_nb_helper_class.return_value = mock_nb_helper

        # Execute
        result = handle_provision_end(mock_conn, mock_nautobot, minimal_event_data)

        # Verify
        assert result == 0

        # Check update_cf was called with minimal fields
        ironic_data = minimal_event_data["payload"]["ironic_object.data"]
        expected_device_uuid = uuid.UUID(ironic_data["uuid"])

        mock_nb_helper.update_cf.assert_called_once_with(
            device_id=expected_device_uuid,
            tenant_id=None,
            fields={
                "ironic_provision_state": "available",
            },
        )

        # Check update_device_status was called
        mock_nb_helper.update_device_status.assert_called_once_with(
            expected_device_uuid, "Planned"
        )

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_no_status_mapping(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when provision state has no Nautobot status mapping."""
        # Setup mocks - return None for intermediate states
        mock_mapper.translate_to_nautobot.return_value = None
        mock_nb_helper = MagicMock()
        mock_nb_helper_class.return_value = mock_nb_helper

        # Execute
        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        # Verify
        assert result == 0

        # Check update_cf was still called
        mock_nb_helper.update_cf.assert_called_once()

        # Check update_device_status was NOT called
        mock_nb_helper.update_device_status.assert_not_called()

    def test_handle_provision_end_missing_payload(self, mock_conn, mock_nautobot):
        """Test handling with missing payload."""
        event_data = {}

        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        assert result == 1

    def test_handle_provision_end_missing_ironic_object_data(
        self, mock_conn, mock_nautobot
    ):
        """Test handling with missing ironic_object.data."""
        event_data = {"payload": {"other_field": "value"}}

        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        assert result == 1

    def test_handle_provision_end_missing_uuid(self, mock_conn, mock_nautobot):
        """Test handling with missing node UUID."""
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "provision_state": "active",
                }
            }
        }

        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        assert result == 1

    def test_handle_provision_end_missing_provision_state(
        self, mock_conn, mock_nautobot
    ):
        """Test handling with missing provision state."""
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "uuid": str(uuid.uuid4()),
                }
            }
        }

        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        assert result == 1

    def test_handle_provision_end_invalid_node_uuid(self, mock_conn, mock_nautobot):
        """Test handling with invalid node UUID format."""
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "uuid": "not-a-valid-uuid",
                    "provision_state": "active",
                }
            }
        }

        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        assert result == 1

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_invalid_lessee_uuid(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
    ):
        """Test handling with invalid lessee UUID (should log warning but continue)."""
        # Setup mocks
        mock_mapper.translate_to_nautobot.return_value = "Active"
        mock_nb_helper = MagicMock()
        mock_nb_helper_class.return_value = mock_nb_helper

        event_data = {
            "payload": {
                "ironic_object.data": {
                    "uuid": str(uuid.uuid4()),
                    "provision_state": "active",
                    "lessee": "not-a-valid-uuid",
                }
            }
        }

        # Execute
        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        # Should succeed but with tenant_id=None
        assert result == 0

        # Check update_cf was called with tenant_id=None
        call_args = mock_nb_helper.update_cf.call_args
        assert call_args[1]["tenant_id"] is None

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_nautobot_update_cf_fails(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when Nautobot update_cf fails."""
        # Setup mocks
        mock_mapper.translate_to_nautobot.return_value = "Active"
        mock_nb_helper = MagicMock()
        mock_nb_helper.update_cf.side_effect = Exception("Nautobot API error")
        mock_nb_helper_class.return_value = mock_nb_helper

        # Execute
        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        # Should return error
        assert result == 1

        # update_device_status should not be called
        mock_nb_helper.update_device_status.assert_not_called()

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_nautobot_update_status_fails(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when Nautobot update_device_status fails."""
        # Setup mocks
        mock_mapper.translate_to_nautobot.return_value = "Active"
        mock_nb_helper = MagicMock()
        mock_nb_helper.update_cf.return_value = True
        mock_nb_helper.update_device_status.side_effect = Exception(
            "Status update failed"
        )
        mock_nb_helper_class.return_value = mock_nb_helper

        # Execute
        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        # Should return error
        assert result == 1

        # update_cf should have been called
        mock_nb_helper.update_cf.assert_called_once()

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_different_provision_states(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
    ):
        """Test handling different provision states."""
        mock_nb_helper = MagicMock()
        mock_nb_helper_class.return_value = mock_nb_helper

        test_cases = [
            ("available", "Planned"),
            ("active", "Active"),
            ("deploying", "Staged"),
            ("deploy failed", "Quarantine"),
            ("error", "Quarantine"),
            ("inspecting", "Inventory"),
        ]

        for provision_state, expected_status in test_cases:
            # Reset mocks
            mock_mapper.reset_mock()
            mock_nb_helper.reset_mock()

            # Setup
            mock_mapper.translate_to_nautobot.return_value = expected_status

            event_data = {
                "payload": {
                    "ironic_object.data": {
                        "uuid": str(uuid.uuid4()),
                        "provision_state": provision_state,
                    }
                }
            }

            # Execute
            result = handle_provision_end(mock_conn, mock_nautobot, event_data)

            # Verify
            assert result == 0
            mock_mapper.translate_to_nautobot.assert_called_once_with(provision_state)
            mock_nb_helper.update_device_status.assert_called_once()
            status_call_args = mock_nb_helper.update_device_status.call_args
            assert status_call_args[0][1] == expected_status

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_with_resource_class(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
    ):
        """Test handling with different resource classes."""
        mock_mapper.translate_to_nautobot.return_value = "Active"
        mock_nb_helper = MagicMock()
        mock_nb_helper_class.return_value = mock_nb_helper

        resource_classes = ["baremetal", "compute", "storage", "network"]

        for resource_class in resource_classes:
            # Reset mocks
            mock_nb_helper.reset_mock()

            event_data = {
                "payload": {
                    "ironic_object.data": {
                        "uuid": str(uuid.uuid4()),
                        "provision_state": "active",
                        "resource_class": resource_class,
                    }
                }
            }

            # Execute
            result = handle_provision_end(mock_conn, mock_nautobot, event_data)

            # Verify
            assert result == 0
            call_args = mock_nb_helper.update_cf.call_args
            assert call_args[1]["fields"]["resource_class"] == resource_class

    @patch("understack_workflows.oslo_event.provision_state_sync.NautobotHelper")
    @patch("understack_workflows.oslo_event.provision_state_sync.ProvisionStateMapper")
    def test_handle_provision_end_uuid_formats(
        self,
        mock_mapper,
        mock_nb_helper_class,
        mock_conn,
        mock_nautobot,
    ):
        """Test handling with different UUID formats (with/without dashes)."""
        mock_mapper.translate_to_nautobot.return_value = "Active"
        mock_nb_helper = MagicMock()
        mock_nb_helper_class.return_value = mock_nb_helper

        # Test with UUID object
        node_uuid_obj = uuid.uuid4()
        lessee_uuid_obj = uuid.uuid4()

        event_data = {
            "payload": {
                "ironic_object.data": {
                    "uuid": str(node_uuid_obj),
                    "provision_state": "active",
                    "lessee": str(lessee_uuid_obj),
                }
            }
        }

        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        assert result == 0

        # Verify UUIDs were converted correctly
        call_args = mock_nb_helper.update_cf.call_args
        assert call_args[1]["device_id"] == node_uuid_obj
        assert call_args[1]["tenant_id"] == lessee_uuid_obj
