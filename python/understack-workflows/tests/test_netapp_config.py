"""Tests for NetApp configuration management."""

import os
import tempfile
from unittest.mock import patch

import pytest

from understack_workflows.netapp.config import NetAppConfig
from understack_workflows.netapp.exceptions import ConfigurationError


class TestNetAppConfig:
    """Test cases for NetAppConfig class."""

    @pytest.fixture
    def valid_config_file(self):
        """Create a valid temporary config file for testing."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname.example.com
netapp_login = test-user
netapp_password = test-password-123
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def config_with_nic_prefix(self):
        """Create a config file with custom NIC slot prefix."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname.example.com
netapp_login = test-user
netapp_password = test-password-123
netapp_nic_slot_prefix = e5
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    @pytest.fixture
    def minimal_config_file(self):
        """Create a minimal valid config file."""
        config_content = """[netapp_nvme]
netapp_server_hostname = host
netapp_login = user
netapp_password = pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_successful_initialization(self, valid_config_file):
        """Test successful NetAppConfig initialization."""
        config = NetAppConfig(valid_config_file)

        assert config.hostname == "test-hostname.example.com"
        assert config.username == "test-user"
        assert config.password == "test-password-123"
        assert config.netapp_nic_slot_prefix == "e4"  # Default value
        assert config.config_path == valid_config_file

    def test_default_config_path(self):
        """Test NetAppConfig with default config path."""
        with patch.object(NetAppConfig, "_parse_config") as mock_parse:
            mock_parse.return_value = {
                "hostname": "default-host",
                "username": "default-user",
                "password": "default-pass",
            }

            config = NetAppConfig()

            assert config.config_path == "/etc/netapp/netapp_nvme.conf"
            mock_parse.assert_called_once()

    def test_file_not_found(self):
        """Test ConfigurationError when config file doesn't exist."""
        with pytest.raises(ConfigurationError) as exc_info:
            NetAppConfig("/nonexistent/path/config.conf")

        error = exc_info.value
        assert "Configuration file not found" in error.message
        assert error.config_path == "/nonexistent/path/config.conf"

    def test_missing_section(self):
        """Test ConfigurationError when required section is missing."""
        config_content = """[wrong_section]
some_key = some_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Missing required configuration" in error.message
            assert error.config_path == f.name
            assert "missing_config" in error.context

        os.unlink(f.name)

    def test_missing_hostname_option(self):
        """Test ConfigurationError when hostname option is missing."""
        config_content = """[netapp_nvme]
netapp_login = test-user
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Missing required configuration" in error.message
            assert "netapp_server_hostname" in str(error)

        os.unlink(f.name)

    def test_missing_username_option(self):
        """Test ConfigurationError when username option is missing."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Missing required configuration" in error.message
            assert "netapp_login" in str(error)

        os.unlink(f.name)

    def test_missing_password_option(self):
        """Test ConfigurationError when password option is missing."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login = test-user
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Missing required configuration" in error.message
            assert "netapp_password" in str(error)

        os.unlink(f.name)

    def test_empty_hostname_value(self):
        """Test ConfigurationError when hostname value is empty."""
        config_content = """[netapp_nvme]
netapp_server_hostname =
netapp_login = test-user
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: hostname" in error.message
            assert "empty_fields" in error.context
            assert "hostname" in error.context["empty_fields"]

        os.unlink(f.name)

    def test_empty_username_value(self):
        """Test ConfigurationError when username value is empty."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login =
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: username" in error.message

        os.unlink(f.name)

    def test_empty_password_value(self):
        """Test ConfigurationError when password value is empty."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login = test-user
netapp_password =
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: password" in error.message

        os.unlink(f.name)

    def test_multiple_empty_fields(self):
        """Test ConfigurationError when multiple fields are empty."""
        config_content = """[netapp_nvme]
netapp_server_hostname =
netapp_login =
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: hostname, username" in error.message
            assert len(error.context["empty_fields"]) == 2

        os.unlink(f.name)

    def test_whitespace_only_values(self):
        """Test ConfigurationError when values contain only whitespace."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login =
netapp_password =
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: username, password" in error.message

        os.unlink(f.name)

    def test_malformed_config_file(self):
        """Test ConfigurationError when config file is malformed."""
        config_content = """[netapp_nvme
netapp_server_hostname = test-hostname
invalid line without equals
netapp_login = test-user
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name)

            error = exc_info.value
            assert "Failed to parse configuration file" in error.message
            assert "parsing_error" in error.context

        os.unlink(f.name)

    def test_validate_method_directly(self, valid_config_file):
        """Test calling validate method directly."""
        config = NetAppConfig(valid_config_file)

        # Should not raise any exception
        config.validate()

    def test_properties_immutable(self, valid_config_file):
        """Test that config properties are read-only."""
        config = NetAppConfig(valid_config_file)

        # Properties should not be settable
        with pytest.raises(AttributeError):
            config.hostname = "new-hostname"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            config.username = "new-user"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            config.password = "new-password"  # type: ignore[misc]

    def test_config_with_extra_sections(self, valid_config_file):
        """Test config parsing ignores extra sections."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login = test-user
netapp_password = test-password

[extra_section]
extra_key = extra_value

[another_section]
another_key = another_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            config = NetAppConfig(f.name)

            assert config.hostname == "test-hostname"
            assert config.username == "test-user"
            assert config.password == "test-password"

        os.unlink(f.name)

    def test_netapp_nic_slot_prefix_custom_value(self, config_with_nic_prefix):
        """Test NetAppConfig with custom NIC slot prefix."""
        config = NetAppConfig(config_with_nic_prefix)

        assert config.hostname == "test-hostname.example.com"
        assert config.username == "test-user"
        assert config.password == "test-password-123"
        assert config.netapp_nic_slot_prefix == "e5"

    def test_netapp_nic_slot_prefix_default_value(self, valid_config_file):
        """Test NetAppConfig uses default NIC slot prefix when not specified."""
        config = NetAppConfig(valid_config_file)

        assert config.netapp_nic_slot_prefix == "e4"

    def test_config_with_extra_options(self):
        """Test config parsing ignores extra options in netapp_nvme section."""
        config_content = """[netapp_nvme]
netapp_server_hostname = test-hostname
netapp_login = test-user
netapp_password = test-password
extra_option = extra_value
another_option = another_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            config = NetAppConfig(f.name)

            assert config.hostname == "test-hostname"
            assert config.username == "test-user"
            assert config.password == "test-password"

        os.unlink(f.name)
    def test_integration_netapp_config_with_from_nautobot_response(self, config_with_nic_prefix):
        """Test integration between NetAppConfig and NetappIPInterfaceConfig.from_nautobot_response."""
        from unittest.mock import MagicMock
        from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig
        import ipaddress

        # Create config with custom NIC prefix
        config = NetAppConfig(config_with_nic_prefix)
        assert config.netapp_nic_slot_prefix == "e5"

        # Create a mock nautobot response
        mock_interface_a = MagicMock()
        mock_interface_a.name = "N1-test-A"
        mock_interface_a.address = "192.168.1.10/24"
        mock_interface_a.vlan = 100

        mock_interface_b = MagicMock()
        mock_interface_b.name = "N1-test-B"
        mock_interface_b.address = "192.168.1.11/24"
        mock_interface_b.vlan = 100

        mock_response = MagicMock()
        mock_response.interfaces = [mock_interface_a, mock_interface_b]

        # Test that from_nautobot_response uses the custom prefix
        configs = NetappIPInterfaceConfig.from_nautobot_response(mock_response, config)

        assert len(configs) == 2
        assert configs[0].base_port_name == "e5a"
        assert configs[1].base_port_name == "e5b"
        assert configs[0].nic_slot_prefix == "e5"
        assert configs[1].nic_slot_prefix == "e5"
    def test_from_nautobot_response_default_prefix(self, valid_config_file):
        """Test that from_nautobot_response uses default prefix when no config provided."""
        from unittest.mock import MagicMock
        from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig

        # Create a mock nautobot response
        mock_interface = MagicMock()
        mock_interface.name = "N1-test-A"
        mock_interface.address = "192.168.1.10/24"
        mock_interface.vlan = 100

        mock_response = MagicMock()
        mock_response.interfaces = [mock_interface]

        # Test without config (should use default)
        configs = NetappIPInterfaceConfig.from_nautobot_response(mock_response)
        assert len(configs) == 1
        assert configs[0].base_port_name == "e4a"
        assert configs[0].nic_slot_prefix == "e4"

        # Test with config that has default prefix
        config = NetAppConfig(valid_config_file)
        configs_with_config = NetappIPInterfaceConfig.from_nautobot_response(mock_response, config)
        assert len(configs_with_config) == 1
        assert configs_with_config[0].base_port_name == "e4a"
        assert configs_with_config[0].nic_slot_prefix == "e4"