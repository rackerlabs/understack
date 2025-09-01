"""Integration tests for NetAppManager cleanup_project orchestration.

This module tests the enhanced cleanup_project method with cross-service
error scenarios and rollback logic.
"""

import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError
from understack_workflows.netapp.manager import NetAppManager


class TestNetAppManagerCleanupIntegration:
    """Integration tests for cleanup_project orchestration."""

    @pytest.fixture
    def mock_config_file(self):
        """Create a temporary config file for testing."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login = test-user
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_both_exist_both_succeed(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when both volume and SVM exist and both deletions succeed."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.cleanup_project("test-project-123")

        # Verify both services were called correctly
        manager._volume_service.exists.assert_called_once_with("test-project-123")
        manager._svm_service.exists.assert_called_once_with("test-project-123")
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project-123", force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with("test-project-123")

        # Verify result
        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_volume_fails_svm_skipped(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when volume deletion fails and SVM deletion is skipped."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods - volume deletion fails
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=False)
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project("test-project-123")

        # Verify volume deletion was attempted
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project-123", force=True
        )

        # Verify SVM deletion was NOT attempted due to volume failure
        manager._svm_service.delete_svm.assert_not_called()

        # Verify result
        assert result == {"volume": False, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_volume_succeeds_svm_fails(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when volume deletion succeeds but SVM deletion fails."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods - SVM deletion fails
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=False)

        result = manager.cleanup_project("test-project-123")

        # Verify both services were called
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project-123", force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with("test-project-123")

        # Verify result shows inconsistent state
        assert result == {"volume": True, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_neither_exist(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when neither volume nor SVM exist."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods - nothing exists
        manager._volume_service.exists = MagicMock(return_value=False)
        manager._svm_service.exists = MagicMock(return_value=False)
        manager._volume_service.delete_volume = MagicMock()
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project("test-project-123")

        # Verify existence checks were made
        manager._volume_service.exists.assert_called_once_with("test-project-123")
        manager._svm_service.exists.assert_called_once_with("test-project-123")

        # Verify no deletion attempts were made
        manager._volume_service.delete_volume.assert_not_called()
        manager._svm_service.delete_svm.assert_not_called()

        # Verify result - both considered "successfully deleted" since they don't exist
        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_only_volume_exists(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when only volume exists."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods - only volume exists
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=False)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project("test-project-123")

        # Verify volume deletion was attempted
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project-123", force=True
        )

        # Verify SVM deletion was not attempted since it doesn't exist
        manager._svm_service.delete_svm.assert_not_called()

        # Verify result
        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_only_svm_exists(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when only SVM exists."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods - only SVM exists
        manager._volume_service.exists = MagicMock(return_value=False)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock()
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.cleanup_project("test-project-123")

        # Verify volume deletion was not attempted since it doesn't exist
        manager._volume_service.delete_volume.assert_not_called()

        # Verify SVM deletion was attempted (since no volume to block it)
        manager._svm_service.delete_svm.assert_called_once_with("test-project-123")

        # Verify result
        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_existence_check_fails(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when existence checks fail with exceptions."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods - existence checks fail
        manager._volume_service.exists = MagicMock(
            side_effect=Exception("Connection error")
        )
        manager._svm_service.exists = MagicMock(
            side_effect=Exception("Connection error")
        )
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.cleanup_project("test-project-123")

        # Verify existence checks were attempted
        manager._volume_service.exists.assert_called_once_with("test-project-123")
        manager._svm_service.exists.assert_called_once_with("test-project-123")

        # Verify cleanup still proceeds (assumes both exist when check fails)
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project-123", force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with("test-project-123")

        # Verify result
        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_volume_exception_during_deletion(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when volume deletion raises an exception."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods - volume deletion raises exception
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(
            side_effect=VolumeOperationError("Volume busy")
        )
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project("test-project-123")

        # Verify volume deletion was attempted
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project-123", force=True
        )

        # Verify SVM deletion was not attempted due to volume failure
        manager._svm_service.delete_svm.assert_not_called()

        # Verify result shows volume failure
        assert result == {"volume": False, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_svm_exception_during_deletion(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when SVM deletion raises an exception."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods - SVM deletion raises exception
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(
            side_effect=SvmOperationError("SVM has dependencies")
        )

        result = manager.cleanup_project("test-project-123")

        # Verify both services were called
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project-123", force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with("test-project-123")

        # Verify result shows SVM failure but volume success (inconsistent state)
        assert result == {"volume": True, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_behavior(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that cleanup_project maintains the same return format as before."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods for successful cleanup
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.cleanup_project("test-project-123")

        # Verify the return format matches the original implementation
        assert isinstance(result, dict)
        assert "volume" in result
        assert "svm" in result
        assert isinstance(result["volume"], bool)
        assert isinstance(result["svm"], bool)
        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_logging_behavior(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that cleanup_project logs appropriate messages during orchestration."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=False)  # SVM fails

        with patch("understack_workflows.netapp.manager.logger") as mock_logger:
            result = manager.cleanup_project("test-project-123")

            # Verify appropriate log messages were called
            mock_logger.info.assert_any_call(
                "Starting cleanup for project: %s", "test-project-123"
            )
            mock_logger.info.assert_any_call(
                "Successfully deleted volume for project: %s", "test-project-123"
            )
            mock_logger.warning.assert_any_call(
                "Failed to delete SVM for project: %s", "test-project-123"
            )
            mock_logger.warning.assert_any_call(
                "Partial cleanup failure for project %s - Volume: %s, SVM: %s",
                "test-project-123",
                True,
                False,
            )

        assert result == {"volume": True, "svm": False}
