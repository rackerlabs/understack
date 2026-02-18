import json
import uuid
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.oslo_event.ironic_node import IronicProvisionSetEvent
from understack_workflows.oslo_event.ironic_node import create_volume_connector
from understack_workflows.oslo_event.ironic_node import handle_provision_end
from understack_workflows.oslo_event.ironic_node import instance_nqn


class TestIronicProvisionSetEvent:
    """Test cases for IronicProvisionSetEvent class."""

    def test_from_event_dict_success(self):
        """Test successful event parsing with real JSON data."""
        # Load real event data from JSON sample
        json_file = (
            "tests/json_samples/ironic_versioned_notifications_server_provisioned.json"
        )
        with open(json_file) as f:
            sample_data = json.load(f)

        # Parse the oslo message to get the actual event data
        oslo_message = json.loads(sample_data["oslomessage"])

        # Create event data in the format expected by from_event_dict
        event_data = {
            "payload": oslo_message["payload"],
        }

        event = IronicProvisionSetEvent.from_event_dict(event_data)

        # Verify the parsed values match the real data (strings as stored in JSON)
        # owner and lessee are undashed UUIDs in the sample
        assert event.owner == "32e02632f4f04415bab5895d1e7247b7"
        assert event.lessee == "5f5955bc89e148e59a12110a3945e4d7"
        # instance_uuid and node_uuid have dashes in the sample
        assert event.instance_uuid == "5027885e-52a8-48f9-adf4-14d8f5f4ccb8"
        assert event.node_uuid == "461737c4-037c-41bf-9c17-f4f33ff20dd7"
        assert event.event == "done"

    def test_from_event_dict_no_payload(self):
        """Test event parsing with missing payload."""
        event_data = {"instance_uuid": str(uuid.uuid4())}

        with pytest.raises(ValueError, match="Invalid event. No 'payload'"):
            IronicProvisionSetEvent.from_event_dict(event_data)

    def test_from_event_dict_no_ironic_object_data(self):
        """Test event parsing with missing ironic_object.data."""
        event_data = {
            "payload": {"other_field": "value"},
        }

        with pytest.raises(
            ValueError, match="Invalid event. No 'ironic_object.data' in payload"
        ):
            IronicProvisionSetEvent.from_event_dict(event_data)

    def test_from_event_dict_missing_required_fields(self):
        """Test event parsing with missing required fields in ironic_object.data."""
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "owner": str(uuid.uuid4()),
                    # Missing lessee, event, uuid
                }
            },
        }

        with pytest.raises(KeyError):
            IronicProvisionSetEvent.from_event_dict(event_data)

    def test_direct_initialization(self):
        """Test direct initialization of IronicProvisionSetEvent."""
        owner_uuid = str(uuid.uuid4())
        lessee_uuid = str(uuid.uuid4())
        instance_uuid = str(uuid.uuid4())
        node_uuid = str(uuid.uuid4())
        event_type = "provision_end"

        event = IronicProvisionSetEvent(
            owner=owner_uuid,
            lessee=lessee_uuid,
            instance_uuid=instance_uuid,
            node_uuid=node_uuid,
            event=event_type,
        )

        assert event.owner == owner_uuid
        assert event.lessee == lessee_uuid
        assert event.instance_uuid == instance_uuid
        assert event.node_uuid == node_uuid
        assert event.event == event_type


class TestHandleProvisionEnd:
    """Test cases for handle_provision_end function."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock OpenStack connection."""
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        """Create a mock Nautobot instance."""
        return MagicMock()

    @pytest.fixture
    def valid_event_data(self):
        """Create valid event data for testing."""
        return {
            "payload": {
                "ironic_object.data": {
                    "instance_uuid": str(uuid.uuid4()),
                    "owner": str(uuid.uuid4()),
                    "lessee": str(uuid.uuid4()),
                    "event": "provision_end",
                    "uuid": str(uuid.uuid4()),
                }
            },
        }

    def test_handle_provision_end_no_payload_data(self, mock_conn, mock_nautobot):
        """Test handling when payload data cannot be extracted."""
        invalid_event_data = {"payload": None}

        result = handle_provision_end(mock_conn, mock_nautobot, invalid_event_data)

        assert result == 1

    def test_handle_provision_end_no_lessee(self, mock_conn, mock_nautobot):
        """Test handling when lessee is missing (not an instance deployment)."""
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "instance_uuid": str(uuid.uuid4()),
                    "owner": str(uuid.uuid4()),
                    "lessee": None,
                    "event": "done",
                    "uuid": str(uuid.uuid4()),
                }
            },
        }

        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        assert result == 0

    def test_handle_provision_end_no_instance_uuid(self, mock_conn, mock_nautobot):
        """Test handling when instance_uuid is missing (not an instance deployment)."""
        event_data = {
            "payload": {
                "ironic_object.data": {
                    "instance_uuid": None,
                    "owner": str(uuid.uuid4()),
                    "lessee": str(uuid.uuid4()),
                    "event": "done",
                    "uuid": str(uuid.uuid4()),
                }
            },
        }

        result = handle_provision_end(mock_conn, mock_nautobot, event_data)

        assert result == 0

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_project_not_svm_enabled(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when project is not SVM enabled."""
        mock_is_svm_enabled.return_value = False
        mock_server = MagicMock()
        mock_server.id = "server-123"
        mock_server.metadata = {"storage": "not-wanted"}
        mock_conn.get_server_by_id.return_value = mock_server

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        lessee = valid_event_data["payload"]["ironic_object.data"]["lessee"]
        lessee_undashed = uuid.UUID(lessee).hex
        mock_is_svm_enabled.assert_called_once_with(mock_conn, lessee_undashed)
        mock_save_output.assert_any_call("storage", "not-set")
        mock_create_connector.assert_called_once()

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_server_not_found(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when server is not found."""
        mock_is_svm_enabled.return_value = True
        mock_conn.get_server_by_id.return_value = None

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 1
        instance_uuid = valid_event_data["payload"]["ironic_object.data"][
            "instance_uuid"
        ]
        mock_conn.get_server_by_id.assert_called_once_with(instance_uuid)
        mock_save_output.assert_called_once_with("storage", "not-found")
        mock_create_connector.assert_not_called()

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_storage_wanted(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when server wants storage."""
        mock_is_svm_enabled.return_value = True
        mock_server = MagicMock()
        mock_server.id = "server-123"
        mock_server.metadata = {"storage": "wanted"}
        mock_conn.get_server_by_id.return_value = mock_server

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        ironic_data = valid_event_data["payload"]["ironic_object.data"]
        instance_uuid = ironic_data["instance_uuid"]
        node_uuid = ironic_data["uuid"]

        mock_conn.get_server_by_id.assert_called_once_with(instance_uuid)

        # Check save_output calls
        expected_calls = [
            ("storage", "wanted"),
            ("node_uuid", node_uuid),
            ("instance_uuid", instance_uuid),
        ]
        actual_calls = [call.args for call in mock_save_output.call_args_list]
        assert actual_calls == expected_calls

        mock_create_connector.assert_called_once()

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_storage_not_wanted(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when server does not want storage."""
        mock_is_svm_enabled.return_value = True
        mock_server = MagicMock()
        mock_server.id = "server-123"
        mock_server.metadata = {"storage": "not-wanted"}
        mock_conn.get_server_by_id.return_value = mock_server

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        ironic_data = valid_event_data["payload"]["ironic_object.data"]
        instance_uuid = ironic_data["instance_uuid"]
        node_uuid = ironic_data["uuid"]

        mock_conn.get_server_by_id.assert_called_once_with(instance_uuid)

        # Check save_output calls
        expected_calls = [
            ("storage", "not-set"),
            ("node_uuid", node_uuid),
            ("instance_uuid", instance_uuid),
        ]
        actual_calls = [call.args for call in mock_save_output.call_args_list]
        assert actual_calls == expected_calls

        mock_create_connector.assert_called_once()

    @patch("understack_workflows.oslo_event.ironic_node.create_volume_connector")
    @patch("understack_workflows.oslo_event.ironic_node.save_output")
    @patch("understack_workflows.oslo_event.ironic_node.is_project_svm_enabled")
    def test_handle_provision_end_storage_metadata_missing(
        self,
        mock_is_svm_enabled,
        mock_save_output,
        mock_create_connector,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when server metadata doesn't have storage key."""
        mock_is_svm_enabled.return_value = True
        mock_server = MagicMock()
        mock_server.id = "server-123"
        mock_server.metadata = {"other_key": "value"}
        mock_conn.get_server_by_id.return_value = mock_server

        result = handle_provision_end(mock_conn, mock_nautobot, valid_event_data)

        # Should return 0 and set storage to "not-set" (uses .get())
        assert result == 0
        ironic_data = valid_event_data["payload"]["ironic_object.data"]
        instance_uuid = ironic_data["instance_uuid"]
        node_uuid = ironic_data["uuid"]

        expected_calls = [
            ("storage", "not-set"),
            ("node_uuid", node_uuid),
            ("instance_uuid", instance_uuid),
        ]
        actual_calls = [call.args for call in mock_save_output.call_args_list]
        assert actual_calls == expected_calls


class TestCreateVolumeConnector:
    """Test cases for create_volume_connector function."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock OpenStack connection."""
        return MagicMock()

    @pytest.fixture
    def sample_event(self):
        """Create a sample IronicProvisionSetEvent."""
        return IronicProvisionSetEvent(
            owner=str(uuid.uuid4()),
            lessee=str(uuid.uuid4()),
            instance_uuid=str(uuid.uuid4()),
            node_uuid=str(uuid.uuid4()),
            event="provision_end",
        )

    def test_create_volume_connector_success(self, mock_conn, sample_event):
        """Test successful volume connector creation."""
        mock_connector = MagicMock()
        mock_conn.baremetal.create_volume_connector.return_value = mock_connector

        result = create_volume_connector(mock_conn, sample_event)

        assert result == mock_connector
        expected_nqn = f"nqn.2014-08.org.nvmexpress:uuid:{sample_event.instance_uuid}"
        mock_conn.baremetal.create_volume_connector.assert_called_once_with(
            node_uuid=sample_event.node_uuid,
            type="iqn",
            connector_id=expected_nqn,
        )

    def test_create_volume_connector_with_different_instance_uuid(
        self, mock_conn, sample_event
    ):
        """Test volume connector creation with different instance UUID."""
        different_instance_uuid = str(uuid.uuid4())
        sample_event.instance_uuid = different_instance_uuid

        mock_connector = MagicMock()
        mock_conn.baremetal.create_volume_connector.return_value = mock_connector

        result = create_volume_connector(mock_conn, sample_event)

        assert result == mock_connector
        expected_nqn = f"nqn.2014-08.org.nvmexpress:uuid:{different_instance_uuid}"
        mock_conn.baremetal.create_volume_connector.assert_called_once_with(
            node_uuid=sample_event.node_uuid,
            type="iqn",
            connector_id=expected_nqn,
        )

    def test_create_volume_connector_baremetal_exception(self, mock_conn, sample_event):
        """Test handling when baremetal connector creation fails."""
        mock_conn.baremetal.create_volume_connector.side_effect = Exception(
            "Baremetal service error"
        )

        with pytest.raises(Exception, match="Baremetal service error"):
            create_volume_connector(mock_conn, sample_event)

        mock_conn.baremetal.create_volume_connector.assert_called_once()


class TestInstanceNqn:
    """Test cases for instance_nqn function."""

    def test_instance_nqn_format(self):
        """Test NQN format generation."""
        test_uuid = str(uuid.uuid4())
        expected_nqn = f"nqn.2014-08.org.nvmexpress:uuid:{test_uuid}"

        result = instance_nqn(test_uuid)

        assert result == expected_nqn

    def test_instance_nqn_different_uuids(self):
        """Test NQN generation with different UUIDs."""
        uuid1 = str(uuid.uuid4())
        uuid2 = str(uuid.uuid4())

        nqn1 = instance_nqn(uuid1)
        nqn2 = instance_nqn(uuid2)

        assert nqn1 != nqn2
        assert nqn1 == f"nqn.2014-08.org.nvmexpress:uuid:{uuid1}"
        assert nqn2 == f"nqn.2014-08.org.nvmexpress:uuid:{uuid2}"

    def test_instance_nqn_prefix_constant(self):
        """Test that NQN prefix is consistent."""
        test_uuid = str(uuid.uuid4())
        result = instance_nqn(test_uuid)

        assert result.startswith("nqn.2014-08.org.nvmexpress:uuid:")
        assert test_uuid in result

    def test_instance_nqn_with_known_uuid(self):
        """Test NQN generation with a known UUID string."""
        known_uuid_str = "12345678-1234-5678-9abc-123456789abc"
        expected_nqn = f"nqn.2014-08.org.nvmexpress:uuid:{known_uuid_str}"

        result = instance_nqn(known_uuid_str)

        assert result == expected_nqn
