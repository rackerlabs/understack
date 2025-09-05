"""Consolidated integration tests for NetAppManager cross-service coordination."""

import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError
from understack_workflows.netapp.manager import NetAppManager


class TestNetAppManagerIntegration:
    """Integration tests for NetAppManager cross-service coordination."""

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

    # ========================================================================
    # Service Coordination Tests
    # ========================================================================

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_service_initialization_coordination(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that all services are properly initialized and coordinated."""
        manager = NetAppManager(mock_config_file)

        # Verify all services are initialized with proper dependencies
        from understack_workflows.netapp.client import NetAppClient
        from understack_workflows.netapp.config import NetAppConfig
        from understack_workflows.netapp.error_handler import ErrorHandler
        from understack_workflows.netapp.lif_service import LifService
        from understack_workflows.netapp.svm_service import SvmService
        from understack_workflows.netapp.volume_service import VolumeService

        assert isinstance(manager._client, NetAppClient)
        assert isinstance(manager._config, NetAppConfig)
        assert isinstance(manager._error_handler, ErrorHandler)
        assert isinstance(manager._svm_service, SvmService)
        assert isinstance(manager._volume_service, VolumeService)
        assert isinstance(manager._lif_service, LifService)

        # Verify services share the same client and error handler instances
        assert manager._svm_service._client is manager._client
        assert manager._svm_service._error_handler is manager._error_handler
        assert manager._volume_service._client is manager._client
        assert manager._volume_service._error_handler is manager._error_handler
        assert manager._lif_service._client is manager._client
        assert manager._lif_service._error_handler is manager._error_handler

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cross_service_error_propagation(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test error propagation across service boundaries."""
        manager = NetAppManager(mock_config_file)

        # Test SVM service error propagation
        manager._svm_service.create_svm = MagicMock(
            side_effect=SvmOperationError("SVM creation failed")
        )

        with pytest.raises(SvmOperationError, match="SVM creation failed"):
            manager.create_svm("test-project", "test-aggregate")

        # Test Volume service error propagation
        manager._volume_service.create_volume = MagicMock(
            side_effect=VolumeOperationError("Volume creation failed")
        )

        with pytest.raises(VolumeOperationError, match="Volume creation failed"):
            manager.create_volume("test-project", "1TB", "test-aggregate")

    # ========================================================================
    # Cleanup Project Integration Tests
    # ========================================================================

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_full_success_coordination(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful coordination between services during cleanup."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"

        # Mock all service methods for successful cleanup
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.cleanup_project(project_id)

        # Verify service coordination sequence
        manager._volume_service.exists.assert_called_once_with(project_id)
        manager._svm_service.exists.assert_called_once_with(project_id)
        manager._volume_service.delete_volume.assert_called_once_with(
            project_id, force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with(project_id)

        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_volume_failure_coordination(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test coordination when volume deletion fails."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"

        # Mock volume deletion failure
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=False)
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project(project_id)

        # Verify volume service was called but SVM service was not
        manager._volume_service.delete_volume.assert_called_once_with(
            project_id, force=True
        )
        manager._svm_service.delete_svm.assert_not_called()

        assert result == {"volume": False, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_partial_failure_coordination(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test coordination when volume succeeds but SVM deletion fails."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"

        # Mock volume success, SVM failure
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=False)

        result = manager.cleanup_project(project_id)

        # Verify both services were called
        manager._volume_service.delete_volume.assert_called_once_with(
            project_id, force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with(project_id)

        assert result == {"volume": True, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_nonexistent_resources_coordination(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test coordination when resources don't exist."""
        manager = NetAppManager(mock_config_file)
        project_id = "nonexistent-project"

        # Mock resources don't exist
        manager._volume_service.exists = MagicMock(return_value=False)
        manager._svm_service.exists = MagicMock(return_value=False)
        manager._volume_service.delete_volume = MagicMock()
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project(project_id)

        # Verify no deletion attempts were made
        manager._volume_service.delete_volume.assert_not_called()
        manager._svm_service.delete_svm.assert_not_called()

        # When resources don't exist, cleanup considers them successfully "deleted"
        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_mixed_existence_scenarios(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup coordination with mixed resource existence scenarios."""
        # Scenario 1: Only volume exists
        manager = NetAppManager(mock_config_file)
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=False)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project("test-project-1")

        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project-1", force=True
        )
        manager._svm_service.delete_svm.assert_not_called()
        assert result == {"volume": True, "svm": True}

        # Scenario 2: Only SVM exists (create new manager instance)
        manager2 = NetAppManager(mock_config_file)
        manager2._volume_service.exists = MagicMock(return_value=False)
        manager2._svm_service.exists = MagicMock(return_value=True)
        manager2._volume_service.delete_volume = MagicMock()
        manager2._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager2.cleanup_project("test-project-2")

        manager2._volume_service.delete_volume.assert_not_called()
        manager2._svm_service.delete_svm.assert_called_once_with("test-project-2")
        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_exception_handling_coordination(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test exception handling during cleanup coordination."""
        # Test volume service exception
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"

        manager._volume_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(
            side_effect=VolumeOperationError("Volume deletion failed")
        )
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project(project_id)

        # Verify SVM deletion was not attempted due to volume deletion failure
        manager._svm_service.delete_svm.assert_not_called()
        assert result == {"volume": False, "svm": False}

        # Test SVM service exception after successful volume deletion (new
        # manager instance)
        manager2 = NetAppManager(mock_config_file)
        manager2._volume_service.exists = MagicMock(return_value=True)
        manager2._volume_service.delete_volume = MagicMock(return_value=True)
        manager2._svm_service.exists = MagicMock(return_value=True)
        manager2._svm_service.delete_svm = MagicMock(
            side_effect=SvmOperationError("SVM has dependencies")
        )

        result = manager2.cleanup_project(project_id)

        # Verify both services were called despite SVM failure
        manager2._volume_service.delete_volume.assert_called_once_with(
            project_id, force=True
        )
        manager2._svm_service.delete_svm.assert_called_once_with(project_id)
        assert result == {"volume": True, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_existence_check_failures(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup coordination when existence checks fail."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"

        # Mock existence check failures
        manager._volume_service.exists = MagicMock(
            side_effect=Exception("Connection error")
        )
        manager._svm_service.exists = MagicMock(
            side_effect=Exception("Connection error")
        )
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.cleanup_project(project_id)

        # Verify cleanup still proceeds (assumes both exist when check fails)
        manager._volume_service.delete_volume.assert_called_once_with(
            project_id, force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with(project_id)
        assert result == {"volume": True, "svm": True}

    # ========================================================================
    # Cross-Service Workflow Tests
    # ========================================================================

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_end_to_end_project_lifecycle(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test complete project lifecycle across all services."""
        manager = NetAppManager(mock_config_file)
        project_id = "lifecycle-test-project"

        # Mock successful creation workflow
        manager._svm_service.create_svm = MagicMock(return_value=f"os-{project_id}")
        manager._volume_service.create_volume = MagicMock(
            return_value=f"vol_{project_id}"
        )
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.exists = MagicMock(return_value=True)

        # Mock successful cleanup workflow
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        # Test creation phase
        svm_result = manager.create_svm(project_id, "test-aggregate")
        volume_result = manager.create_volume(project_id, "1TB", "test-aggregate")

        assert svm_result == f"os-{project_id}"
        assert volume_result == f"vol_{project_id}"

        # Test cleanup phase
        cleanup_result = manager.cleanup_project(project_id)

        assert cleanup_result == {"volume": True, "svm": True}

        # Verify all service interactions
        manager._svm_service.create_svm.assert_called_once_with(
            project_id, "test-aggregate"
        )
        manager._volume_service.create_volume.assert_called_once_with(
            project_id, "1TB", "test-aggregate"
        )
        manager._volume_service.delete_volume.assert_called_once_with(
            project_id, force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with(project_id)

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_service_state_consistency_across_operations(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that service state remains consistent across multiple operations."""
        manager = NetAppManager(mock_config_file)

        # Verify all services share the same dependencies
        client_id = id(manager._client)
        error_handler_id = id(manager._error_handler)

        assert id(manager._svm_service._client) == client_id
        assert id(manager._volume_service._client) == client_id
        assert id(manager._lif_service._client) == client_id

        assert id(manager._svm_service._error_handler) == error_handler_id
        assert id(manager._volume_service._error_handler) == error_handler_id
        assert id(manager._lif_service._error_handler) == error_handler_id

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_logging_coordination_across_services(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that logging is properly coordinated across services."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=False)  # SVM fails

        with patch("understack_workflows.netapp.manager.logger") as mock_logger:
            result = manager.cleanup_project("test-project-123")

            # Verify appropriate log messages were called at manager level
            mock_logger.info.assert_any_call(
                "Starting cleanup for project: %(project_id)s",
                {"project_id": "test-project-123"},
            )
            mock_logger.info.assert_any_call(
                "Successfully deleted volume for project: %(project_id)s",
                {"project_id": "test-project-123"},
            )
            mock_logger.warning.assert_any_call(
                "Failed to delete SVM for project: %(project_id)s",
                {"project_id": "test-project-123"},
            )

        assert result == {"volume": True, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_backward_compatibility_maintained(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that refactored manager maintains backward compatibility."""
        manager = NetAppManager(mock_config_file)

        # Mock all service methods to avoid actual calls
        manager._svm_service.create_svm = MagicMock(return_value="test-svm")
        manager._svm_service.delete_svm = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.create_volume = MagicMock(return_value="test-volume")
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._volume_service.get_mapped_namespaces = MagicMock(return_value=[])
        manager._lif_service.create_lif = MagicMock()
        manager._lif_service.create_home_port = MagicMock()
        manager._lif_service.identify_home_node = MagicMock()

        # Test all public methods maintain their original signatures and behavior
        try:
            # Core SVM/Volume operations
            assert manager.create_svm("project", "aggregate") == "test-svm"
            assert manager.delete_svm("os-project") is True
            assert manager.create_volume("project", "1TB", "aggregate") == "test-volume"
            assert manager.delete_volume("vol_project") is True
            assert manager.delete_volume("vol_project", force=True) is True
            assert manager.check_if_svm_exists("project") is True
            assert manager.mapped_namespaces("os-project", "vol_project") == []

            # Cleanup operation
            cleanup_result = manager.cleanup_project("project")
            assert isinstance(cleanup_result, dict)
            assert "volume" in cleanup_result
            assert "svm" in cleanup_result

            # Network operations
            import ipaddress

            from understack_workflows.netapp.value_objects import (
                NetappIPInterfaceConfig,
            )

            config_obj = NetappIPInterfaceConfig(
                name="N3-lif-A",
                address=ipaddress.IPv4Address("192.168.1.1"),
                network=ipaddress.IPv4Network("192.168.1.0/24"),
                vlan_id=100,
            )
            manager.create_lif("project", config_obj)
            manager.create_home_port(config_obj)
            manager.identify_home_node(config_obj)

        except (TypeError, AttributeError) as e:
            pytest.fail(f"Backward compatibility broken: {e}")
