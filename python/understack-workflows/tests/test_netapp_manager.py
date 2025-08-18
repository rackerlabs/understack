import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from netapp_ontap.error import NetAppRestError

from understack_workflows.netapp_manager import NetAppManager


class TestNetAppManager:
    """Test cases for NetAppManager class."""

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

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_init_success(self, mock_host_connection, mock_config, mock_config_file):
        """Test successful NetAppManager initialization."""
        NetAppManager(mock_config_file)

        mock_host_connection.assert_called_once_with(
            "test-hostname", username="test-user", password="test-password"
        )

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_init_default_config_path(self, mock_host_connection, mock_config):
        """Test NetAppManager initialization with default config path."""
        with patch.object(NetAppManager, "parse_ontap_config") as mock_parse:
            mock_parse.return_value = {
                "hostname": "default-host",
                "username": "default-user",
                "password": "default-pass",
            }

            NetAppManager()

            mock_parse.assert_called_once_with("/etc/netapp/netapp_nvme.conf")
            mock_host_connection.assert_called_once_with(
                "default-host", username="default-user", password="default-pass"
            )

    def test_parse_ontap_config_success(self, mock_config_file):
        """Test successful config parsing."""
        manager = NetAppManager.__new__(NetAppManager)
        result = manager.parse_ontap_config(mock_config_file)

        expected = {
            "hostname": "test-hostname",
            "username": "test-user",
            "password": "test-password",
        }
        assert result == expected

    def test_parse_ontap_config_file_not_found(self):
        """Test config parsing when file doesn't exist."""
        manager = NetAppManager.__new__(NetAppManager)

        with pytest.raises(SystemExit) as exc_info:
            manager.parse_ontap_config("/nonexistent/path")

        assert exc_info.value.code == 1

    def test_parse_ontap_config_missing_section(self):
        """Test config parsing with missing section."""
        config_content = """[wrong_section]
some_key = some_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            manager = NetAppManager.__new__(NetAppManager)

            with pytest.raises(SystemExit) as exc_info:
                manager.parse_ontap_config(f.name)

            assert exc_info.value.code == 1

        os.unlink(f.name)

    def test_parse_ontap_config_missing_option(self):
        """Test config parsing with missing required option."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login = test-user
# missing netapp_password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            manager = NetAppManager.__new__(NetAppManager)

            with pytest.raises(SystemExit) as exc_info:
                manager.parse_ontap_config(f.name)

            assert exc_info.value.code == 1

        os.unlink(f.name)

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Svm")
    def test_create_svm_success(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful SVM creation."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.name = "os-test-project-123"
        mock_svm_class.return_value = mock_svm_instance

        manager = NetAppManager(mock_config_file)
        manager.create_svm("test-project-123", "test-aggregate")

        mock_svm_class.assert_called_once_with(
            name="os-test-project-123",
            aggregates=[{"name": "test-aggregate"}],
            language="c.utf_8",
            root_volume={"name": "os-test-project-123_root", "security_style": "unix"},
            allowed_protocols=["nvme"],
            nvme={"enabled": True},
        )
        mock_svm_instance.post.assert_called_once()
        mock_svm_instance.get.assert_called_once()

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Svm")
    def test_create_svm_failure(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test SVM creation failure."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.post.side_effect = NetAppRestError("Test error")
        mock_svm_class.return_value = mock_svm_instance

        manager = NetAppManager(mock_config_file)

        with pytest.raises(SystemExit) as exc_info:
            manager.create_svm("test-project-123", "test-aggregate")

        assert exc_info.value.code == 1

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Volume")
    def test_create_volume_success(
        self, mock_volume_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful volume creation."""
        mock_volume_instance = MagicMock()
        mock_volume_class.return_value = mock_volume_instance

        manager = NetAppManager(mock_config_file)
        manager.create_volume("test-project-123", "1TB", "test-aggregate")

        mock_volume_class.assert_called_once_with(
            name="vol_test-project-123",
            svm={"name": "os-test-project-123"},
            aggregates=[{"name": "test-aggregate"}],
            size="1TB",
        )
        mock_volume_instance.post.assert_called_once()
        mock_volume_instance.get.assert_called_once()

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Volume")
    def test_create_volume_failure(
        self, mock_volume_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test volume creation failure."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.post.side_effect = NetAppRestError("Test error")
        mock_volume_class.return_value = mock_volume_instance

        manager = NetAppManager(mock_config_file)

        with pytest.raises(SystemExit) as exc_info:
            manager.create_volume("test-project-123", "1TB", "test-aggregate")

        assert exc_info.value.code == 1

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_svm_name(self, mock_host_connection, mock_config, mock_config_file):
        """Test SVM name generation."""
        manager = NetAppManager(mock_config_file)
        assert manager._svm_name("test-project-123") == "os-test-project-123"

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_volume_name(self, mock_host_connection, mock_config, mock_config_file):
        """Test volume name generation."""
        manager = NetAppManager(mock_config_file)
        assert manager._volume_name("test-project-123") == "vol_test-project-123"
