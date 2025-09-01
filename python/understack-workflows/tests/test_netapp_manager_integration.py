"""Integration tests for NetAppManager service coordination."""

import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError
from understack_workflows.netapp.manager import NetAppManager


class TestNetAppManagerIntegration:
    """Integration tests for NetAppManager service coordination."""

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

        # Verify service coordination
        manager._volume_service.exists.assert_called_once_with(project_id)
        manager._svm_service.exists.assert_called_once_with(project_id)
        manager._volume_service.delete_volume.assert_called_once_with(
            project_id, force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with(project_id)

        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_volume_failure_stops_svm_deletion(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that SVM deletion is skipped when volume deletion fails."""
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
    def test_cleanup_project_volume_success_svm_failure(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test handling when volume deletion succeeds but SVM deletion fails."""
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
    def test_cleanup_project_nonexistent_resources(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup when resources don't exist."""
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
    def test_cleanup_project_exception_handling(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test exception handling during cleanup coordination."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"

        # Mock volume service to raise exception
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(
            side_effect=VolumeOperationError("Volume deletion failed")
        )
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock()

        # The cleanup_project method catches exceptions and returns failure status
        result = manager.cleanup_project(project_id)

        # Verify SVM deletion was not attempted due to volume deletion failure
        manager._svm_service.delete_svm.assert_not_called()
        assert result == {"volume": False, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_service_method_delegation_create_svm(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that create_svm properly delegates to SvmService."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"
        aggregate = "test-aggregate"

        manager._svm_service.create_svm = MagicMock(return_value="os-test-project-123")

        result = manager.create_svm(project_id, aggregate)

        manager._svm_service.create_svm.assert_called_once_with(project_id, aggregate)
        assert result == "os-test-project-123"

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_service_method_delegation_create_volume(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that create_volume properly delegates to VolumeService."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"
        size = "1TB"
        aggregate = "test-aggregate"

        manager._volume_service.create_volume = MagicMock(
            return_value="vol_test-project-123"
        )

        result = manager.create_volume(project_id, size, aggregate)

        manager._volume_service.create_volume.assert_called_once_with(
            project_id, size, aggregate
        )
        assert result == "vol_test-project-123"

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_service_method_delegation_check_svm_exists(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that check_if_svm_exists properly delegates to SvmService."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"

        manager._svm_service.exists = MagicMock(return_value=True)

        result = manager.check_if_svm_exists(project_id)

        manager._svm_service.exists.assert_called_once_with(project_id)
        assert result is True

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_error_propagation_across_services(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that errors from services are properly propagated."""
        manager = NetAppManager(mock_config_file)
        project_id = "test-project-123"

        # Test SVM service error propagation
        manager._svm_service.create_svm = MagicMock(
            side_effect=SvmOperationError("SVM creation failed")
        )

        with pytest.raises(SvmOperationError, match="SVM creation failed"):
            manager.create_svm(project_id, "test-aggregate")

        # Test Volume service error propagation
        manager._volume_service.create_volume = MagicMock(
            side_effect=VolumeOperationError("Volume creation failed")
        )

        with pytest.raises(VolumeOperationError, match="Volume creation failed"):
            manager.create_volume(project_id, "1TB", "test-aggregate")

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_method_signatures(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that all public method signatures remain unchanged."""
        manager = NetAppManager(mock_config_file)

        # Mock all service methods
        manager._svm_service.create_svm = MagicMock(return_value="test-svm")
        manager._svm_service.delete_svm = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.create_volume = MagicMock(return_value="test-volume")
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._volume_service.get_mapped_namespaces = MagicMock(return_value=[])
        manager._lif_service.create_lif = MagicMock()
        manager._lif_service.create_home_port = MagicMock()
        manager._lif_service.identify_home_node = MagicMock()

        # Test all public methods can be called with expected signatures
        try:
            manager.create_svm("project", "aggregate")
            manager.delete_svm("svm-name")
            # Note: delete_svm doesn't have a force parameter
            manager.create_volume("project", "1TB", "aggregate")
            manager.delete_volume("volume-name")
            manager.delete_volume("volume-name", force=True)  # Optional parameter
            manager.check_if_svm_exists("project")
            manager.mapped_namespaces("svm", "volume")
            manager.cleanup_project("project")

            # Network-related methods would need proper mock objects
            # but we're testing method signatures
            import ipaddress

            from understack_workflows.netapp.value_objects import (
                NetappIPInterfaceConfig,
            )

            mock_config_obj = NetappIPInterfaceConfig(
                name="test",
                address=ipaddress.IPv4Address("192.168.1.1"),
                network=ipaddress.IPv4Network("192.168.1.0/24"),
                vlan_id=100,
            )
            manager.create_lif("project", mock_config_obj)
            manager.create_home_port(mock_config_obj)
            manager.identify_home_node(mock_config_obj)

        except TypeError as e:
            pytest.fail(f"Method signature changed: {e}")

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_service_initialization_dependency_injection(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that services are properly initialized with dependency injection."""
        manager = NetAppManager(mock_config_file)

        # Verify all services are initialized
        assert hasattr(manager, "_client")
        assert hasattr(manager, "_config")
        assert hasattr(manager, "_error_handler")
        assert hasattr(manager, "_svm_service")
        assert hasattr(manager, "_volume_service")
        assert hasattr(manager, "_lif_service")

        # Verify services have the expected types
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
