from unittest.mock import MagicMock
from unittest.mock import call
from unittest.mock import patch

import pytest

from understack_workflows.oslo_event.keystone_project import AGGREGATE_NAME
from understack_workflows.oslo_event.keystone_project import SVM_PROJECT_TAG
from understack_workflows.oslo_event.keystone_project import VOLUME_SIZE
from understack_workflows.oslo_event.keystone_project import KeystoneProjectEvent
from understack_workflows.oslo_event.keystone_project import _keystone_project_tags
from understack_workflows.oslo_event.keystone_project import handle_project_created
from understack_workflows.oslo_event.keystone_project import handle_project_deleted
from understack_workflows.oslo_event.keystone_project import handle_project_updated


class TestKeystoneProjectEvent:
    """Test cases for KeystoneProjectEvent class."""

    def test_from_event_dict_success(self):
        """Test successful event parsing."""
        event_data = {"payload": {"target": {"id": "test-project-123"}}}

        event = KeystoneProjectEvent.from_event_dict(event_data)
        assert event.project_id == "test-project-123"

    def test_from_event_dict_no_payload(self):
        """Test event parsing with missing payload."""
        event_data = {}

        with pytest.raises(Exception, match="Invalid event. No 'payload'"):
            KeystoneProjectEvent.from_event_dict(event_data)

    def test_from_event_dict_no_target(self):
        """Test event parsing with missing target."""
        event_data = {"payload": {}}

        with pytest.raises(Exception, match="no target information in payload"):
            KeystoneProjectEvent.from_event_dict(event_data)

    def test_from_event_dict_no_project_id(self):
        """Test event parsing with missing project ID."""
        event_data = {"payload": {"target": {}}}

        with pytest.raises(Exception, match="no project_id found in payload"):
            KeystoneProjectEvent.from_event_dict(event_data)

    def test_dataclass_initialization(self):
        """Test direct dataclass initialization."""
        event = KeystoneProjectEvent("test-project-456")
        assert event.project_id == "test-project-456"


class TestKeystoneProjectTags:
    """Test cases for _keystone_project_tags function."""

    def test_project_tags_with_tags(self):
        """Test getting project tags when project has tags."""
        mock_project = MagicMock()
        mock_project.tags = ["tag1", "tag2", SVM_PROJECT_TAG]

        mock_conn = MagicMock()
        mock_conn.identity.get_project.return_value = mock_project

        tags = _keystone_project_tags(mock_conn, "test-project-id")

        assert tags == ["tag1", "tag2", SVM_PROJECT_TAG]
        mock_conn.identity.get_project.assert_called_once_with("test-project-id")

    def test_project_tags_no_tags_attribute(self):
        """Test getting project tags when project has no tags attribute."""
        mock_project = MagicMock()
        del mock_project.tags  # Remove tags attribute

        mock_conn = MagicMock()
        mock_conn.identity.get_project.return_value = mock_project

        tags = _keystone_project_tags(mock_conn, "test-project-id")

        assert tags == []
        mock_conn.identity.get_project.assert_called_once_with("test-project-id")

    def test_project_tags_empty_tags(self):
        """Test getting project tags when project has empty tags."""
        mock_project = MagicMock()
        mock_project.tags = []

        mock_conn = MagicMock()
        mock_conn.identity.get_project.return_value = mock_project

        tags = _keystone_project_tags(mock_conn, "test-project-id")

        assert tags == []
        mock_conn.identity.get_project.assert_called_once_with("test-project-id")


class TestHandleProjectCreated:
    """Test cases for handle_project_created function."""

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
            "event_type": "identity.project.created",
            "payload": {"target": {"id": "test-project-123"}},
        }

    def test_handle_project_created_wrong_event_type(self, mock_conn, mock_nautobot):
        """Test handling event with wrong event type."""
        event_data = {
            "event_type": "identity.project.updated",
            "payload": {"target": {"id": "test-project-123"}},
        }

        result = handle_project_created(mock_conn, mock_nautobot, event_data)
        assert result == 1

    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_created_no_svm_tag(
        self, mock_open, mock_tags, mock_conn, mock_nautobot, valid_event_data
    ):
        """Test handling project creation without SVM tag."""
        mock_tags.return_value = ["tag1", "tag2"]
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        result = handle_project_created(mock_conn, mock_nautobot, valid_event_data)
        assert result == 0
        mock_tags.assert_called_once_with(mock_conn, "test-project-123")

        # Verify both project_tags and svm_enabled files are written
        expected_calls = [
            call("/var/run/argo/output.project_tags", "w"),
            call("/var/run/argo/output.svm_enabled", "w"),
        ]
        mock_open.assert_has_calls(expected_calls, any_order=True)

        # Check that JSON-encoded tags were written
        write_calls = mock_file.write.call_args_list
        json_tags_written = False
        for call_args in write_calls:
            if call_args[0][0] == '["tag1", "tag2"]':
                json_tags_written = True
                break
        assert json_tags_written, "Project tags should be written as JSON"

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_created_with_svm_tag(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test successful project creation handling with SVM tag."""
        mock_tags.return_value = ["tag1", SVM_PROJECT_TAG, "tag2"]
        mock_netapp_manager = MagicMock()
        mock_netapp_class.return_value = mock_netapp_manager
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        result = handle_project_created(mock_conn, mock_nautobot, valid_event_data)

        assert result == 0
        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_class.assert_called_once()
        mock_netapp_manager.create_svm.assert_called_once_with(
            project_id="test-project-123", aggregate_name=AGGREGATE_NAME
        )
        mock_netapp_manager.create_volume.assert_called_once_with(
            project_id="test-project-123",
            volume_size=VOLUME_SIZE,
            aggregate_name=AGGREGATE_NAME,
        )

        # Verify project tags are written as JSON
        expected_calls = [
            call("/var/run/argo/output.project_tags", "w"),
            call("/var/run/argo/output.svm_enabled", "w"),
            call("/var/run/argo/output.svm_created", "w"),
            call("/var/run/argo/output.svm_name", "w"),
        ]
        mock_open.assert_has_calls(expected_calls, any_order=True)

        # Check that JSON-encoded tags were written
        write_calls = mock_file.write.call_args_list
        json_tags_written = False
        for call_args in write_calls:
            if call_args[0][0] == '["tag1", "UNDERSTACK_SVM", "tag2"]':
                json_tags_written = True
                break
        assert json_tags_written, "Project tags should be written as JSON"

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_created_netapp_manager_failure(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when NetAppManager creation fails."""
        mock_tags.return_value = [SVM_PROJECT_TAG]
        mock_netapp_class.side_effect = Exception("NetApp connection failed")

        with pytest.raises(Exception, match="NetApp connection failed"):
            handle_project_created(mock_conn, mock_nautobot, valid_event_data)

        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_class.assert_called_once()
        mock_open.assert_called()

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_created_svm_creation_failure(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when SVM creation fails."""
        mock_tags.return_value = [SVM_PROJECT_TAG]
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.create_svm.side_effect = Exception("SVM creation failed")
        mock_netapp_class.return_value = mock_netapp_manager

        with pytest.raises(Exception, match="SVM creation failed"):
            handle_project_created(mock_conn, mock_nautobot, valid_event_data)

        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_class.assert_called_once()
        mock_netapp_manager.create_svm.assert_called_once_with(
            project_id="test-project-123", aggregate_name=AGGREGATE_NAME
        )

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_created_volume_creation_failure(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_event_data,
    ):
        """Test handling when volume creation fails."""
        mock_tags.return_value = [SVM_PROJECT_TAG]
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.create_volume.side_effect = Exception(
            "Volume creation failed"
        )
        mock_netapp_class.return_value = mock_netapp_manager

        with pytest.raises(Exception, match="Volume creation failed"):
            handle_project_created(mock_conn, mock_nautobot, valid_event_data)

        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_class.assert_called_once()
        mock_netapp_manager.create_svm.assert_called_once_with(
            project_id="test-project-123", aggregate_name=AGGREGATE_NAME
        )
        mock_netapp_manager.create_volume.assert_called_once_with(
            project_id="test-project-123",
            volume_size=VOLUME_SIZE,
            aggregate_name=AGGREGATE_NAME,
        )

    def test_handle_project_created_invalid_event_data(self, mock_conn, mock_nautobot):
        """Test handling with invalid event data."""
        invalid_event_data = {
            "event_type": "identity.project.created",
            "payload": {},  # Missing target
        }

        with pytest.raises(Exception, match="no target information in payload"):
            handle_project_created(mock_conn, mock_nautobot, invalid_event_data)

    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_created_constants_used(
        self, mock_open, mock_tags, mock_conn, mock_nautobot, valid_event_data
    ):
        """Test constants used for aggregate name and volume size."""
        mock_tags.return_value = [SVM_PROJECT_TAG]

        with patch(
            "understack_workflows.oslo_event.keystone_project.NetAppManager"
        ) as mock_netapp_class:
            mock_netapp_manager = MagicMock()
            mock_netapp_class.return_value = mock_netapp_manager

            handle_project_created(mock_conn, mock_nautobot, valid_event_data)

            # Verify the constants are used correctly
            mock_netapp_manager.create_svm.assert_called_once_with(
                project_id="test-project-123",
                aggregate_name="aggr02_n02_NVME",  # AGGREGATE_NAME constant
            )
            mock_netapp_manager.create_volume.assert_called_once_with(
                project_id="test-project-123",
                volume_size="514GB",  # VOLUME_SIZE constant
                aggregate_name="aggr02_n02_NVME",  # AGGREGATE_NAME constant
            )
        mock_open.assert_called()

    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_created_json_tags_output(
        self, mock_open, mock_tags, mock_conn, mock_nautobot, valid_event_data
    ):
        """Test that project tags are written as JSON to output file."""
        test_tags = ["custom_tag", "another_tag", SVM_PROJECT_TAG]
        mock_tags.return_value = test_tags
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        with patch(
            "understack_workflows.oslo_event.keystone_project.NetAppManager"
        ) as mock_netapp_class:
            mock_netapp_manager = MagicMock()
            mock_netapp_class.return_value = mock_netapp_manager

            result = handle_project_created(mock_conn, mock_nautobot, valid_event_data)

            assert result == 0

            # Verify project_tags file is written
            mock_open.assert_any_call("/var/run/argo/output.project_tags", "w")

            # Check that the exact JSON representation of tags was written
            import json

            expected_json = json.dumps(test_tags)
            mock_file.write.assert_any_call(expected_json)


class TestHandleProjectUpdated:
    """Test cases for handle_project_updated function."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock OpenStack connection."""
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        """Create a mock Nautobot instance."""
        return MagicMock()

    @pytest.fixture
    def valid_update_event_data(self):
        """Create valid update event data for testing."""
        return {
            "event_type": "identity.project.updated",
            "payload": {"target": {"id": "test-project-123"}},
        }

    def test_handle_project_updated_wrong_event_type(self, mock_conn, mock_nautobot):
        """Test handling event with wrong event type."""
        event_data = {
            "event_type": "identity.project.created",
            "payload": {"target": {"id": "test-project-123"}},
        }

        result = handle_project_updated(mock_conn, mock_nautobot, event_data)
        assert result == 1

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_svm_tag_added(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_update_event_data,
    ):
        """Test project update when SVM_UNDERSTACK tag is added."""
        # Project now has SVM tag
        test_tags = ["tag1", SVM_PROJECT_TAG, "tag2"]
        mock_tags.return_value = test_tags
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = (
            False  # SVM doesn't exist yet
        )
        mock_netapp_manager.create_svm.return_value = "os-test-project-123"
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_project_updated(
            mock_conn, mock_nautobot, valid_update_event_data
        )

        assert result == 0
        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        mock_netapp_manager.create_svm.assert_called_once_with(
            project_id="test-project-123", aggregate_name=AGGREGATE_NAME
        )
        mock_netapp_manager.create_volume.assert_called_once_with(
            project_id="test-project-123",
            volume_size=VOLUME_SIZE,
            aggregate_name=AGGREGATE_NAME,
        )

        # Verify project tags are written as JSON
        mock_open.assert_any_call("/var/run/argo/output.project_tags", "w")
        import json

        expected_json = json.dumps(test_tags)
        mock_file.write.assert_any_call(expected_json)

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_svm_tag_removed(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_update_event_data,
    ):
        """Test project update when SVM_UNDERSTACK tag is removed."""
        # Project no longer has SVM tag
        mock_tags.return_value = ["tag1", "tag2"]

        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = (
            True  # SVM exists but tag removed
        )
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_project_updated(
            mock_conn, mock_nautobot, valid_update_event_data
        )

        assert result == 0
        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        # Should call cleanup_project when tag is removed but SVM exists
        mock_netapp_manager.cleanup_project.assert_called_once_with("test-project-123")
        # Should not create SVM or volume when tag is removed
        mock_netapp_manager.create_svm.assert_not_called()
        mock_netapp_manager.create_volume.assert_not_called()

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_svm_tag_removed_no_svm(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_update_event_data,
    ):
        """Test project update when SVM_UNDERSTACK tag is removed but no SVM exists."""
        # Project no longer has SVM tag
        mock_tags.return_value = ["tag1", "tag2"]

        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = (
            False  # No SVM exists and tag removed
        )
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_project_updated(
            mock_conn, mock_nautobot, valid_update_event_data
        )

        assert result == 0
        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        # Should not call cleanup_project when no SVM exists
        mock_netapp_manager.cleanup_project.assert_not_called()
        # Should not create SVM or volume
        mock_netapp_manager.create_svm.assert_not_called()
        mock_netapp_manager.create_volume.assert_not_called()

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_random_tag_added(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_update_event_data,
    ):
        """Test project update when random_text tag is added (no SVM tag)."""
        # Project has random tag but not SVM tag
        mock_tags.return_value = ["tag1", "random_text", "tag2"]

        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = False
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_project_updated(
            mock_conn, mock_nautobot, valid_update_event_data
        )

        assert result == 0
        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        # Should not create SVM or volume when no SVM tag
        mock_netapp_manager.create_svm.assert_not_called()
        mock_netapp_manager.create_volume.assert_not_called()

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_svm_exists_and_tag_exists(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_update_event_data,
    ):
        """Test project update when SVM tag exists and SVM already exists."""
        # Project has SVM tag and SVM already exists
        mock_tags.return_value = [SVM_PROJECT_TAG, "tag1"]

        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = True
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_project_updated(
            mock_conn, mock_nautobot, valid_update_event_data
        )

        assert result == 0
        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        # Should not create SVM or volume when both exist
        mock_netapp_manager.create_svm.assert_not_called()
        mock_netapp_manager.create_volume.assert_not_called()

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_netapp_manager_failure(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_update_event_data,
    ):
        """Test handling when NetAppManager creation fails during update."""
        mock_tags.return_value = [SVM_PROJECT_TAG]
        mock_netapp_class.side_effect = Exception("NetApp connection failed")

        with pytest.raises(Exception, match="NetApp connection failed"):
            handle_project_updated(mock_conn, mock_nautobot, valid_update_event_data)

        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_class.assert_called_once()

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_svm_creation_failure(
        self,
        mock_open,
        mock_tags,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_update_event_data,
    ):
        """Test handling when SVM creation fails during update."""
        mock_tags.return_value = [SVM_PROJECT_TAG]

        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = False
        mock_netapp_manager.create_svm.side_effect = Exception("SVM creation failed")
        mock_netapp_class.return_value = mock_netapp_manager

        with pytest.raises(Exception, match="SVM creation failed"):
            handle_project_updated(mock_conn, mock_nautobot, valid_update_event_data)

        mock_tags.assert_called_once_with(mock_conn, "test-project-123")
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        mock_netapp_manager.create_svm.assert_called_once_with(
            project_id="test-project-123", aggregate_name=AGGREGATE_NAME
        )

    def test_handle_project_updated_invalid_event_data(self, mock_conn, mock_nautobot):
        """Test handling update with invalid event data."""
        invalid_event_data = {
            "event_type": "identity.project.updated",
            "payload": {},  # Missing target
        }

        with pytest.raises(Exception, match="no target information in payload"):
            handle_project_updated(mock_conn, mock_nautobot, invalid_event_data)

    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_output_files_written(
        self, mock_open, mock_tags, mock_conn, mock_nautobot, valid_update_event_data
    ):
        """Test that output files are written correctly during update."""
        mock_tags.return_value = ["random_tag"]

        with patch(
            "understack_workflows.oslo_event.keystone_project.NetAppManager"
        ) as mock_netapp_class:
            mock_netapp_manager = MagicMock()
            mock_netapp_manager.check_if_svm_exists.return_value = False
            mock_netapp_class.return_value = mock_netapp_manager

            result = handle_project_updated(
                mock_conn, mock_nautobot, valid_update_event_data
            )

            assert result == 0
            # Verify output files are written including project_tags
            expected_calls = [
                call("/var/run/argo/output.project_tags", "w"),
                call("/var/run/argo/output.svm_enabled", "w"),
                call("/var/run/argo/output.svm_name", "w"),
            ]
            mock_open.assert_has_calls(expected_calls, any_order=True)

    @patch("understack_workflows.oslo_event.keystone_project._keystone_project_tags")
    @patch("builtins.open")
    def test_handle_project_updated_json_tags_empty_list(
        self, mock_open, mock_tags, mock_conn, mock_nautobot, valid_update_event_data
    ):
        """Test that empty project tags are written as JSON empty list."""
        mock_tags.return_value = []
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        with patch(
            "understack_workflows.oslo_event.keystone_project.NetAppManager"
        ) as mock_netapp_class:
            mock_netapp_manager = MagicMock()
            mock_netapp_manager.check_if_svm_exists.return_value = False
            mock_netapp_class.return_value = mock_netapp_manager

            result = handle_project_updated(
                mock_conn, mock_nautobot, valid_update_event_data
            )

            assert result == 0

            # Verify project_tags file is written
            mock_open.assert_any_call("/var/run/argo/output.project_tags", "w")

            # Check that empty list JSON was written
            import json

            expected_json = json.dumps([])
            mock_file.write.assert_any_call(expected_json)


class TestHandleProjectDeleted:
    """Test cases for handle_project_deleted function."""

    @pytest.fixture
    def mock_conn(self):
        """Create a mock OpenStack connection."""
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        """Create a mock Nautobot instance."""
        return MagicMock()

    @pytest.fixture
    def valid_delete_event_data(self):
        """Create valid delete event data for testing."""
        return {
            "event_type": "identity.project.deleted",
            "payload": {"target": {"id": "test-project-123"}},
        }

    def test_handle_project_deleted_wrong_event_type(self, mock_conn, mock_nautobot):
        """Test handling event with wrong event type."""
        event_data = {
            "event_type": "identity.project.created",
            "payload": {"target": {"id": "test-project-123"}},
        }

        result = handle_project_deleted(mock_conn, mock_nautobot, event_data)
        assert result == 1

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    def test_handle_project_deleted_svm_exists(
        self,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_delete_event_data,
    ):
        """Test project deletion when SVM exists."""
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = True
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_project_deleted(
            mock_conn, mock_nautobot, valid_delete_event_data
        )

        assert result == 0
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        mock_netapp_manager.cleanup_project.assert_called_once_with("test-project-123")

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    def test_handle_project_deleted_svm_does_not_exist(
        self,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_delete_event_data,
    ):
        """Test project deletion when SVM does not exist."""
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = False
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_project_deleted(
            mock_conn, mock_nautobot, valid_delete_event_data
        )

        assert result == 0
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        mock_netapp_manager.cleanup_project.assert_not_called()

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    def test_handle_project_deleted_netapp_manager_failure(
        self,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_delete_event_data,
    ):
        """Test handling when NetAppManager creation fails during deletion."""
        mock_netapp_class.side_effect = Exception("NetApp connection failed")

        result = handle_project_deleted(
            mock_conn, mock_nautobot, valid_delete_event_data
        )

        assert result == 1  # Should return 1 on exception
        mock_netapp_class.assert_called_once()

    @patch("understack_workflows.oslo_event.keystone_project.NetAppManager")
    def test_handle_project_deleted_cleanup_failure(
        self,
        mock_netapp_class,
        mock_conn,
        mock_nautobot,
        valid_delete_event_data,
    ):
        """Test handling when cleanup_project fails during deletion."""
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = True
        mock_netapp_manager.cleanup_project.side_effect = Exception("Cleanup failed")
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_project_deleted(
            mock_conn, mock_nautobot, valid_delete_event_data
        )

        assert result == 1  # Should return 1 on exception
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id="test-project-123"
        )
        mock_netapp_manager.cleanup_project.assert_called_once_with("test-project-123")

    def test_handle_project_deleted_invalid_event_data(self, mock_conn, mock_nautobot):
        """Test handling deletion with invalid event data."""
        invalid_event_data = {
            "event_type": "identity.project.deleted",
            "payload": {},  # Missing target
        }

        with pytest.raises(Exception, match="no target information in payload"):
            handle_project_deleted(mock_conn, mock_nautobot, invalid_event_data)
