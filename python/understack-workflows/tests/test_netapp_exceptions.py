"""Tests for NetApp custom exception hierarchy."""

from understack_workflows.netapp.exceptions import ConfigurationError
from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.exceptions import NetworkOperationError
from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError


class TestNetAppManagerError:
    """Test cases for NetAppManagerError base exception."""

    def test_basic_exception(self):
        """Test basic exception creation."""
        error = NetAppManagerError("Test error message")

        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.context == {}

    def test_exception_with_context(self):
        """Test exception creation with context."""
        context = {"operation": "test", "resource": "svm"}
        error = NetAppManagerError("Test error", context=context)

        assert error.message == "Test error"
        assert error.context == context

    def test_exception_inheritance(self):
        """Test that NetAppManagerError inherits from Exception."""
        error = NetAppManagerError("Test error")
        assert isinstance(error, Exception)


class TestConfigurationError:
    """Test cases for ConfigurationError."""

    def test_basic_configuration_error(self):
        """Test basic configuration error creation."""
        error = ConfigurationError("Config file not found")

        assert str(error) == "Config file not found"
        assert error.message == "Config file not found"
        assert error.config_path is None
        assert error.context == {}

    def test_configuration_error_with_path(self):
        """Test configuration error with config path."""
        error = ConfigurationError(
            "Invalid config", config_path="/etc/netapp/config.conf"
        )

        assert error.message == "Invalid config"
        assert error.config_path == "/etc/netapp/config.conf"

    def test_configuration_error_with_context(self):
        """Test configuration error with context."""
        context = {"section": "netapp_nvme", "missing_key": "hostname"}
        error = ConfigurationError(
            "Missing configuration", config_path="/etc/config.conf", context=context
        )

        assert error.context == context
        assert error.config_path == "/etc/config.conf"

    def test_configuration_error_inheritance(self):
        """Test ConfigurationError inheritance."""
        error = ConfigurationError("Test error")
        assert isinstance(error, NetAppManagerError)
        assert isinstance(error, Exception)


class TestSvmOperationError:
    """Test cases for SvmOperationError."""

    def test_basic_svm_error(self):
        """Test basic SVM operation error."""
        error = SvmOperationError("SVM creation failed")

        assert str(error) == "SVM creation failed"
        assert error.message == "SVM creation failed"
        assert error.svm_name is None
        assert error.context == {}

    def test_svm_error_with_name(self):
        """Test SVM error with SVM name."""
        error = SvmOperationError("SVM deletion failed", svm_name="os-project-123")

        assert error.message == "SVM deletion failed"
        assert error.svm_name == "os-project-123"

    def test_svm_error_with_context(self):
        """Test SVM error with context."""
        context = {"project_id": "123", "aggregate": "aggr1"}
        error = SvmOperationError(
            "SVM operation failed", svm_name="os-project-123", context=context
        )

        assert error.context == context
        assert error.svm_name == "os-project-123"

    def test_svm_error_inheritance(self):
        """Test SvmOperationError inheritance."""
        error = SvmOperationError("Test error")
        assert isinstance(error, NetAppManagerError)
        assert isinstance(error, Exception)


class TestVolumeOperationError:
    """Test cases for VolumeOperationError."""

    def test_basic_volume_error(self):
        """Test basic volume operation error."""
        error = VolumeOperationError("Volume creation failed")

        assert str(error) == "Volume creation failed"
        assert error.message == "Volume creation failed"
        assert error.volume_name is None
        assert error.context == {}

    def test_volume_error_with_name(self):
        """Test volume error with volume name."""
        error = VolumeOperationError(
            "Volume deletion failed", volume_name="vol_project_123"
        )

        assert error.message == "Volume deletion failed"
        assert error.volume_name == "vol_project_123"

    def test_volume_error_with_context(self):
        """Test volume error with context."""
        context = {"size": "1TB", "aggregate": "aggr1"}
        error = VolumeOperationError(
            "Volume operation failed", volume_name="vol_project_123", context=context
        )

        assert error.context == context
        assert error.volume_name == "vol_project_123"

    def test_volume_error_inheritance(self):
        """Test VolumeOperationError inheritance."""
        error = VolumeOperationError("Test error")
        assert isinstance(error, NetAppManagerError)
        assert isinstance(error, Exception)


class TestNetworkOperationError:
    """Test cases for NetworkOperationError."""

    def test_basic_network_error(self):
        """Test basic network operation error."""
        error = NetworkOperationError("Interface creation failed")

        assert str(error) == "Interface creation failed"
        assert error.message == "Interface creation failed"
        assert error.interface_name is None
        assert error.context == {}

    def test_network_error_with_interface_name(self):
        """Test network error with interface name."""
        error = NetworkOperationError(
            "LIF creation failed", interface_name="N1-storage-A"
        )

        assert error.message == "LIF creation failed"
        assert error.interface_name == "N1-storage-A"

    def test_network_error_with_context(self):
        """Test network error with context."""
        context = {"vlan_id": 100, "node": "node-01"}
        error = NetworkOperationError(
            "Port creation failed", interface_name="N1-storage-A", context=context
        )

        assert error.context == context
        assert error.interface_name == "N1-storage-A"

    def test_network_error_inheritance(self):
        """Test NetworkOperationError inheritance."""
        error = NetworkOperationError("Test error")
        assert isinstance(error, NetAppManagerError)
        assert isinstance(error, Exception)
