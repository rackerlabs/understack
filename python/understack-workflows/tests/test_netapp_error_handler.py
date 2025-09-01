"""Tests for NetApp error handler."""

import logging
from unittest.mock import MagicMock

import pytest
from netapp_ontap.error import NetAppRestError

from understack_workflows.netapp.error_handler import ErrorHandler
from understack_workflows.netapp.exceptions import ConfigurationError
from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.exceptions import NetworkOperationError
from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError


class TestErrorHandler:
    """Test cases for ErrorHandler class."""

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger for testing."""
        return MagicMock(spec=logging.Logger)

    @pytest.fixture
    def error_handler(self, mock_logger):
        """Create an ErrorHandler instance with mock logger."""
        return ErrorHandler(mock_logger)

    def test_initialization(self, mock_logger):
        """Test ErrorHandler initialization."""
        handler = ErrorHandler(mock_logger)
        assert handler._logger == mock_logger

    def test_handle_netapp_error_svm_operation(self, error_handler, mock_logger):
        """Test handling NetApp error for SVM operations."""
        netapp_error = NetAppRestError("SVM creation failed")
        context = {"svm_name": "os-project-123", "aggregate": "aggr1"}

        with pytest.raises(SvmOperationError) as exc_info:
            error_handler.handle_netapp_error(netapp_error, "SVM creation", context)

        error = exc_info.value
        assert "NetApp SVM creation failed" in error.message
        assert error.svm_name == "os-project-123"
        assert "netapp_error" in error.context
        assert error.context["aggregate"] == "aggr1"

        # Verify logging
        mock_logger.error.assert_called_once()
        log_call = mock_logger.error.call_args[0]
        assert "NetApp operation failed" in log_call[0]
        assert "SVM creation" in log_call[1]

    def test_handle_netapp_error_volume_operation(self, error_handler, mock_logger):
        """Test handling NetApp error for volume operations."""
        netapp_error = NetAppRestError("Volume deletion failed")
        context = {"volume_name": "vol_project_123", "force": True}

        with pytest.raises(VolumeOperationError) as exc_info:
            error_handler.handle_netapp_error(netapp_error, "volume deletion", context)

        error = exc_info.value
        assert "NetApp volume deletion failed" in error.message
        assert error.volume_name == "vol_project_123"
        assert error.context["force"] is True

    def test_handle_netapp_error_lif_operation(self, error_handler, mock_logger):
        """Test handling NetApp error for LIF operations."""
        netapp_error = NetAppRestError("LIF creation failed")
        context = {"interface_name": "N1-storage-A", "vlan_id": 100}

        with pytest.raises(NetworkOperationError) as exc_info:
            error_handler.handle_netapp_error(netapp_error, "LIF creation", context)

        error = exc_info.value
        assert "NetApp LIF creation failed" in error.message
        assert error.interface_name == "N1-storage-A"
        assert error.context["vlan_id"] == 100

    def test_handle_netapp_error_interface_operation(self, error_handler, mock_logger):
        """Test handling NetApp error for interface operations."""
        netapp_error = NetAppRestError("Interface configuration failed")
        context = {"interface_name": "N2-storage-B"}

        with pytest.raises(NetworkOperationError) as exc_info:
            error_handler.handle_netapp_error(
                netapp_error, "interface configuration", context
            )

        error = exc_info.value
        assert "NetApp interface configuration failed" in error.message
        assert error.interface_name == "N2-storage-B"

    def test_handle_netapp_error_port_operation(self, error_handler, mock_logger):
        """Test handling NetApp error for port operations."""
        netapp_error = NetAppRestError("Port creation failed")
        context = {"interface_name": "N1-storage-A"}

        with pytest.raises(NetworkOperationError) as exc_info:
            error_handler.handle_netapp_error(netapp_error, "port creation", context)

        error = exc_info.value
        assert "NetApp port creation failed" in error.message

    def test_handle_netapp_error_network_operation(self, error_handler, mock_logger):
        """Test handling NetApp error for network operations."""
        netapp_error = NetAppRestError("Network setup failed")
        context = {"interface_name": "N1-storage-A"}

        with pytest.raises(NetworkOperationError) as exc_info:
            error_handler.handle_netapp_error(netapp_error, "network setup", context)

        error = exc_info.value
        assert "NetApp network setup failed" in error.message

    def test_handle_netapp_error_generic_operation(self, error_handler, mock_logger):
        """Test handling NetApp error for generic operations."""
        netapp_error = NetAppRestError("Generic operation failed")
        context = {"resource": "cluster"}

        with pytest.raises(NetAppManagerError) as exc_info:
            error_handler.handle_netapp_error(
                netapp_error, "cluster configuration", context
            )

        error = exc_info.value
        assert "NetApp cluster configuration failed" in error.message
        assert error.context["resource"] == "cluster"

    def test_handle_netapp_error_no_context(self, error_handler, mock_logger):
        """Test handling NetApp error without context."""
        netapp_error = NetAppRestError("Operation failed")

        with pytest.raises(SvmOperationError) as exc_info:
            error_handler.handle_netapp_error(netapp_error, "SVM operation")

        error = exc_info.value
        assert "NetApp SVM operation failed" in error.message
        assert error.svm_name is None
        assert "netapp_error" in error.context

    def test_handle_config_error(self, error_handler, mock_logger):
        """Test handling configuration errors."""
        config_error = FileNotFoundError("Config file not found")
        config_path = "/etc/netapp/config.conf"
        context = {"section": "netapp_nvme"}

        with pytest.raises(ConfigurationError) as exc_info:
            error_handler.handle_config_error(config_error, config_path, context)

        error = exc_info.value
        assert "Configuration error with /etc/netapp/config.conf" in error.message
        assert error.config_path == config_path
        assert error.context["section"] == "netapp_nvme"
        assert "original_error" in error.context

        # Verify logging
        mock_logger.error.assert_called_once()
        log_call = mock_logger.error.call_args[0]
        assert "Configuration error" in log_call[0]
        assert config_path in log_call[1]

    def test_handle_config_error_no_context(self, error_handler, mock_logger):
        """Test handling configuration error without context."""
        config_error = ValueError("Invalid configuration")
        config_path = "/etc/netapp/config.conf"

        with pytest.raises(ConfigurationError) as exc_info:
            error_handler.handle_config_error(config_error, config_path)

        error = exc_info.value
        assert "Configuration error with /etc/netapp/config.conf" in error.message
        assert error.config_path == config_path
        assert "original_error" in error.context

    def test_handle_operation_error(self, error_handler, mock_logger):
        """Test handling general operation errors."""
        operation_error = RuntimeError("Operation failed")
        operation = "test operation"
        context = {"resource": "test", "action": "create"}

        with pytest.raises(NetAppManagerError) as exc_info:
            error_handler.handle_operation_error(operation_error, operation, context)

        error = exc_info.value
        assert "Operation 'test operation' failed" in error.message
        assert error.context["resource"] == "test"
        assert error.context["action"] == "create"
        assert "original_error" in error.context

        # Verify logging
        mock_logger.error.assert_called_once()
        log_call = mock_logger.error.call_args[0]
        assert "Operation failed" in log_call[0]
        assert operation in log_call[1]

    def test_handle_operation_error_no_context(self, error_handler, mock_logger):
        """Test handling operation error without context."""
        operation_error = Exception("Generic error")
        operation = "generic operation"

        with pytest.raises(NetAppManagerError) as exc_info:
            error_handler.handle_operation_error(operation_error, operation)

        error = exc_info.value
        assert "Operation 'generic operation' failed" in error.message
        assert "original_error" in error.context

    def test_log_warning_with_context(self, error_handler, mock_logger):
        """Test logging warning with context."""
        message = "This is a warning"
        context = {"resource": "svm", "action": "create"}

        error_handler.log_warning(message, context)

        mock_logger.warning.assert_called_once_with(
            "%s - Context: %s", message, context
        )

    def test_log_warning_without_context(self, error_handler, mock_logger):
        """Test logging warning without context."""
        message = "This is a warning"

        error_handler.log_warning(message)

        mock_logger.warning.assert_called_once_with(message)

    def test_log_info_with_context(self, error_handler, mock_logger):
        """Test logging info with context."""
        message = "This is info"
        context = {"operation": "svm_creation", "status": "success"}

        error_handler.log_info(message, context)

        mock_logger.info.assert_called_once_with("%s - Context: %s", message, context)

    def test_log_info_without_context(self, error_handler, mock_logger):
        """Test logging info without context."""
        message = "This is info"

        error_handler.log_info(message)

        mock_logger.info.assert_called_once_with(message)

    def test_log_debug_with_context(self, error_handler, mock_logger):
        """Test logging debug with context."""
        message = "This is debug"
        context = {"details": "verbose information"}

        error_handler.log_debug(message, context)

        mock_logger.debug.assert_called_once_with("%s - Context: %s", message, context)

    def test_log_debug_without_context(self, error_handler, mock_logger):
        """Test logging debug without context."""
        message = "This is debug"

        error_handler.log_debug(message)

        mock_logger.debug.assert_called_once_with(message)

    def test_case_insensitive_operation_matching(self, error_handler, mock_logger):
        """Test that operation type matching is case insensitive."""
        netapp_error = NetAppRestError("Operation failed")

        # Test uppercase SVM
        with pytest.raises(SvmOperationError):
            error_handler.handle_netapp_error(netapp_error, "SVM Creation")

        # Test mixed case volume
        with pytest.raises(VolumeOperationError):
            error_handler.handle_netapp_error(netapp_error, "Volume Deletion")

        # Test uppercase LIF
        with pytest.raises(NetworkOperationError):
            error_handler.handle_netapp_error(netapp_error, "LIF Configuration")

    def test_multiple_operation_keywords(self, error_handler, mock_logger):
        """Test operations with multiple keywords."""
        netapp_error = NetAppRestError("Operation failed")

        # Should match SVM first
        with pytest.raises(SvmOperationError):
            error_handler.handle_netapp_error(netapp_error, "SVM volume configuration")

        # Should match volume when SVM not present
        with pytest.raises(VolumeOperationError):
            error_handler.handle_netapp_error(netapp_error, "volume interface setup")
