from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.oslo_event.cinder_volume_type import (
    CinderVolumeTypeAccessEvent,
)
from understack_workflows.oslo_event.cinder_volume_type import (
    handle_volume_type_access_added,
)
from understack_workflows.oslo_event.cinder_volume_type import (
    handle_volume_type_access_removed,
)
from understack_workflows.oslo_event.constants import AGGREGATE_NAME
from understack_workflows.oslo_event.constants import VOLUME_SIZE

PROJECT_ID = "06f78699-5138-462a-b847-36ecd0e6bf32"
VOLUME_TYPE_ID = "9a479ec0-c29b-4d37-bf9e-9957214a33ae"


class TestCinderVolumeTypeAccessEvent:
    """Tests for CinderVolumeTypeAccessEvent parsing."""

    def test_from_event_dict_success(self):
        event_data = {
            "payload": {
                "project_id": PROJECT_ID,
                "volume_type_id": VOLUME_TYPE_ID,
            }
        }
        event = CinderVolumeTypeAccessEvent.from_event_dict(event_data)
        assert event.project_id == PROJECT_ID
        assert event.volume_type_id == VOLUME_TYPE_ID

    def test_from_event_dict_missing_volume_type_id(self):
        event_data = {"payload": {"project_id": PROJECT_ID}}
        with pytest.raises(Exception, match="no volume_type_id in event payload"):
            CinderVolumeTypeAccessEvent.from_event_dict(event_data)

    def test_from_event_dict_missing_project_id(self):
        event_data = {"payload": {}}
        with pytest.raises(Exception, match="no project_id in event payload"):
            CinderVolumeTypeAccessEvent.from_event_dict(event_data)


class TestHandleVolumeTypeAccessAdded:
    """Tests for handle_volume_type_access_added."""

    @pytest.fixture
    def mock_conn(self):
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    @pytest.fixture
    def valid_event_data(self):
        return {
            "event_type": "volume_type_project.access.add",
            "payload": {
                "project_id": PROJECT_ID,
                "volume_type_id": VOLUME_TYPE_ID,
            },
        }

    def test_wrong_event_type(self, mock_conn, mock_nautobot):
        event_data = {
            "event_type": "volume_type_project.access.remove",
            "payload": {"project_id": PROJECT_ID, "volume_type_id": VOLUME_TYPE_ID},
        }
        result = handle_volume_type_access_added(mock_conn, mock_nautobot, event_data)
        assert result == 1

    @patch("understack_workflows.oslo_event.cinder_volume_type.NetAppManager")
    @patch("builtins.open")
    def test_svm_does_not_exist_returns_1(
        self, mock_open, mock_netapp_class, mock_conn, mock_nautobot, valid_event_data
    ):
        """If SVM doesn't exist, skip volume creation and return 1."""
        mock_conn.block_storage.get_type.return_value = MagicMock(extra_specs={})
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = False
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_volume_type_access_added(
            mock_conn, mock_nautobot, valid_event_data
        )

        assert result == 1
        mock_netapp_manager.check_if_svm_exists.assert_called_once_with(
            project_id=PROJECT_ID
        )
        mock_netapp_manager.create_volume.assert_not_called()

    @patch("understack_workflows.oslo_event.cinder_volume_type.NetAppManager")
    @patch("builtins.open")
    def test_successful_volume_creation(
        self, mock_open, mock_netapp_class, mock_conn, mock_nautobot, valid_event_data
    ):
        """Volume created with correct project_id, volume_type_id, defaults."""
        mock_conn.block_storage.get_type.return_value = MagicMock(extra_specs={})
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = True
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_volume_type_access_added(
            mock_conn, mock_nautobot, valid_event_data
        )

        assert result == 0
        mock_netapp_manager.create_volume.assert_called_once_with(
            project_id=PROJECT_ID,
            volume_type_id=VOLUME_TYPE_ID,
            volume_size=VOLUME_SIZE,
            aggregate_name=AGGREGATE_NAME,
        )

    @patch("understack_workflows.oslo_event.cinder_volume_type.NetAppManager")
    @patch("builtins.open")
    def test_extra_specs_used_for_aggregate_and_size(
        self, mock_open, mock_netapp_class, mock_conn, mock_nautobot, valid_event_data
    ):
        """aggregate_name and volume_size from extra_specs override defaults."""
        mock_conn.block_storage.get_type.return_value = MagicMock(
            extra_specs={
                "aggregate_name": "aggr_custom",
                "volume_size": "1TB",
            }
        )
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.check_if_svm_exists.return_value = True
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_volume_type_access_added(
            mock_conn, mock_nautobot, valid_event_data
        )

        assert result == 0
        mock_netapp_manager.create_volume.assert_called_once_with(
            project_id=PROJECT_ID,
            volume_type_id=VOLUME_TYPE_ID,
            volume_size="1TB",
            aggregate_name="aggr_custom",
        )


class TestHandleVolumeTypeAccessRemoved:
    """Tests for handle_volume_type_access_removed."""

    @pytest.fixture
    def mock_conn(self):
        return MagicMock()

    @pytest.fixture
    def mock_nautobot(self):
        return MagicMock()

    @pytest.fixture
    def valid_event_data(self):
        return {
            "event_type": "volume_type_project.access.remove",
            "payload": {
                "project_id": PROJECT_ID,
                "volume_type_id": VOLUME_TYPE_ID,
            },
        }

    def test_wrong_event_type(self, mock_conn, mock_nautobot):
        event_data = {
            "event_type": "volume_type_project.access.add",
            "payload": {"project_id": PROJECT_ID, "volume_type_id": VOLUME_TYPE_ID},
        }
        result = handle_volume_type_access_removed(mock_conn, mock_nautobot, event_data)
        assert result == 1

    @patch("understack_workflows.oslo_event.cinder_volume_type.NetAppManager")
    @patch("builtins.open")
    def test_successful_volume_deletion(
        self, mock_open, mock_netapp_class, mock_conn, mock_nautobot, valid_event_data
    ):
        """Volume deleted and returns 0 on success."""
        expected_volume_name = f"vol_{VOLUME_TYPE_ID.replace('-', '')}"
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.get_volume_name.return_value = expected_volume_name
        mock_netapp_manager.delete_volume.return_value = True
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_volume_type_access_removed(
            mock_conn, mock_nautobot, valid_event_data
        )

        assert result == 0
        mock_netapp_manager.get_volume_name.assert_called_once_with(VOLUME_TYPE_ID)
        mock_netapp_manager.delete_volume.assert_called_once_with(
            expected_volume_name, force=False
        )

    @patch("understack_workflows.oslo_event.cinder_volume_type.NetAppManager")
    @patch("builtins.open")
    def test_deletion_returns_false_returns_1(
        self, mock_open, mock_netapp_class, mock_conn, mock_nautobot, valid_event_data
    ):
        """Returns 1 when delete_volume returns False."""
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.delete_volume.return_value = False
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_volume_type_access_removed(
            mock_conn, mock_nautobot, valid_event_data
        )

        assert result == 1

    @patch("understack_workflows.oslo_event.cinder_volume_type.NetAppManager")
    @patch("builtins.open")
    def test_deletion_failure_returns_1(
        self, mock_open, mock_netapp_class, mock_conn, mock_nautobot, valid_event_data
    ):
        """Returns 1 when delete_volume raises an exception."""
        mock_netapp_manager = MagicMock()
        mock_netapp_manager.delete_volume.side_effect = Exception("Delete failed")
        mock_netapp_class.return_value = mock_netapp_manager

        result = handle_volume_type_access_removed(
            mock_conn, mock_nautobot, valid_event_data
        )

        assert result == 1
