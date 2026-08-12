"""Tests for NetApp configuration management."""

import os
import tempfile

import pytest

from understack_workflows.netapp.config import NetAppConfig
from understack_workflows.netapp.exceptions import ConfigurationError


class TestNetAppConfig:
    """Test cases for NetAppConfig class."""

    @pytest.fixture
    def valid_config_file(self):
        """Create a valid temporary config file for testing."""
        config_content = """[backend1]
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
        config_content = """[backend1]
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
    def multi_backend_config_file(self):
        """Create a config file with multiple backends."""
        config_content = """[staging-svm1]
netapp_server_hostname = netapp1.staging.example.com
netapp_login = admin1
netapp_password = pass1

[staging-svm2]
netapp_server_hostname = netapp2.staging.example.com
netapp_login = admin2
netapp_password = pass2
netapp_nic_slot_prefix = e2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_successful_initialization(self, valid_config_file):
        """Test successful NetAppConfig initialization."""
        config = NetAppConfig(valid_config_file, "backend1")

        assert config.hostname == "test-hostname.example.com"
        assert config.username == "test-user"
        assert config.password == "test-password-123"
        assert config.netapp_nic_slot_prefix == "e4"  # Default value
        assert config.config_path == valid_config_file
        assert config.section == "backend1"

    def test_file_not_found(self):
        """Test ConfigurationError when config file doesn't exist."""
        with pytest.raises(ConfigurationError) as exc_info:
            NetAppConfig("/nonexistent/path/config.conf", "backend1")

        error = exc_info.value
        assert "Configuration file not found" in error.message
        assert error.config_path == "/nonexistent/path/config.conf"

    def test_missing_section(self):
        """Test ConfigurationError when requested section is missing."""
        config_content = """[other_section]
netapp_server_hostname = test-hostname
netapp_login = test-user
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "nonexistent_section")

            error = exc_info.value
            assert "not found" in error.message
            assert "nonexistent_section" in error.message

        os.unlink(f.name)

    def test_missing_hostname_option(self):
        """Test ConfigurationError when hostname option is missing."""
        config_content = """[backend1]
netapp_login = test-user
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "backend1")

            error = exc_info.value
            assert "Missing required configuration" in error.message
            assert "netapp_server_hostname" in str(error)

        os.unlink(f.name)

    def test_missing_username_option(self):
        """Test ConfigurationError when username option is missing."""
        config_content = """[backend1]
netapp_server_hostname = test-hostname
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "backend1")

            error = exc_info.value
            assert "Missing required configuration" in error.message
            assert "netapp_login" in str(error)

        os.unlink(f.name)

    def test_missing_password_option(self):
        """Test ConfigurationError when password option is missing."""
        config_content = """[backend1]
netapp_server_hostname = test-hostname
netapp_login = test-user
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "backend1")

            error = exc_info.value
            assert "Missing required configuration" in error.message
            assert "netapp_password" in str(error)

        os.unlink(f.name)

    def test_empty_hostname_value(self):
        """Test ConfigurationError when hostname value is empty."""
        config_content = """[backend1]
netapp_server_hostname =
netapp_login = test-user
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "backend1")

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: hostname" in error.message
            assert "empty_fields" in error.context
            assert "hostname" in error.context["empty_fields"]

        os.unlink(f.name)

    def test_empty_username_value(self):
        """Test ConfigurationError when username value is empty."""
        config_content = """[backend1]
netapp_server_hostname = test-hostname
netapp_login =
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "backend1")

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: username" in error.message

        os.unlink(f.name)

    def test_empty_password_value(self):
        """Test ConfigurationError when password value is empty."""
        config_content = """[backend1]
netapp_server_hostname = test-hostname
netapp_login = test-user
netapp_password =
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "backend1")

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: password" in error.message

        os.unlink(f.name)

    def test_multiple_empty_fields(self):
        """Test ConfigurationError when multiple fields are empty."""
        config_content = """[backend1]
netapp_server_hostname =
netapp_login =
netapp_password = test-password
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "backend1")

            error = exc_info.value
            assert "Configuration validation failed" in error.message
            assert "Empty fields: hostname, username" in error.message
            assert len(error.context["empty_fields"]) == 2

        os.unlink(f.name)

    def test_malformed_config_file(self):
        """Test ConfigurationError when config file is malformed."""
        config_content = """[backend1
netapp_server_hostname = test-hostname
invalid line without equals
netapp_login = test-user
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig(f.name, "backend1")

            error = exc_info.value
            assert "Failed to parse configuration file" in error.message
            assert "parsing_error" in error.context

        os.unlink(f.name)

    def test_validate_method_directly(self, valid_config_file):
        """Test calling validate method directly."""
        config = NetAppConfig(valid_config_file, "backend1")

        # Should not raise any exception
        config.validate()

    def test_properties_immutable(self, valid_config_file):
        """Test that config properties are read-only."""
        config = NetAppConfig(valid_config_file, "backend1")

        with pytest.raises(AttributeError):
            config.hostname = "new-hostname"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            config.username = "new-user"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            config.password = "new-password"  # type: ignore[misc]

    def test_netapp_nic_slot_prefix_custom_value(self, config_with_nic_prefix):
        """Test NetAppConfig with custom NIC slot prefix."""
        config = NetAppConfig(config_with_nic_prefix, "backend1")

        assert config.hostname == "test-hostname.example.com"
        assert config.username == "test-user"
        assert config.password == "test-password-123"
        assert config.netapp_nic_slot_prefix == "e5"

    def test_netapp_nic_slot_prefix_default_value(self, valid_config_file):
        """Test NetAppConfig uses default NIC slot prefix when not specified."""
        config = NetAppConfig(valid_config_file, "backend1")

        assert config.netapp_nic_slot_prefix == "e4"

    def test_config_with_extra_options(self):
        """Test config parsing ignores extra options in section."""
        config_content = """[backend1]
netapp_server_hostname = test-hostname
netapp_login = test-user
netapp_password = test-password
extra_option = extra_value
another_option = another_value
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            config = NetAppConfig(f.name, "backend1")

            assert config.hostname == "test-hostname"
            assert config.username == "test-user"
            assert config.password == "test-password"

        os.unlink(f.name)


class TestNetAppConfigGetAllBackends:
    """Test cases for NetAppConfig.get_all_backends()."""

    @pytest.fixture
    def multi_backend_config_file(self):
        """Create a config file with multiple backends."""
        config_content = """[staging-svm1]
netapp_server_hostname = netapp1.staging.example.com
netapp_login = admin1
netapp_password = pass1

[staging-svm2]
netapp_server_hostname = netapp2.staging.example.com
netapp_login = admin2
netapp_password = pass2
netapp_nic_slot_prefix = e2
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()
            yield f.name
        os.unlink(f.name)

    def test_get_all_backends_returns_all_sections(self, multi_backend_config_file):
        """Test that get_all_backends returns one config per section."""
        backends = NetAppConfig.get_all_backends(multi_backend_config_file)

        assert len(backends) == 2
        assert backends[0].section == "staging-svm1"
        assert backends[0].hostname == "netapp1.staging.example.com"
        assert backends[0].username == "admin1"
        assert backends[0].password == "pass1"
        assert backends[0].netapp_nic_slot_prefix == "e4"  # default

        assert backends[1].section == "staging-svm2"
        assert backends[1].hostname == "netapp2.staging.example.com"
        assert backends[1].username == "admin2"
        assert backends[1].password == "pass2"
        assert backends[1].netapp_nic_slot_prefix == "e2"

    def test_get_all_backends_file_not_found(self):
        """Test ConfigurationError when file doesn't exist."""
        with pytest.raises(ConfigurationError) as exc_info:
            NetAppConfig.get_all_backends("/nonexistent/path.conf")

        assert "Configuration file not found" in exc_info.value.message

    def test_get_all_backends_empty_file(self):
        """Test ConfigurationError when file has no sections."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write("# just a comment\n")
            f.flush()

            with pytest.raises(ConfigurationError) as exc_info:
                NetAppConfig.get_all_backends(f.name)

            assert "No sections found" in exc_info.value.message

        os.unlink(f.name)

    def test_get_all_backends_single_section(self):
        """Test get_all_backends with a single section."""
        config_content = """[prod-svm1]
netapp_server_hostname = netapp.prod.example.com
netapp_login = prod-admin
netapp_password = prod-pass
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            backends = NetAppConfig.get_all_backends(f.name)

            assert len(backends) == 1
            assert backends[0].section == "prod-svm1"
            assert backends[0].hostname == "netapp.prod.example.com"

        os.unlink(f.name)

    def test_integration_netapp_config_with_from_nautobot_response(
        self,
    ):
        """Test integration between NetAppConfig and NetappIPInterfaceConfig."""
        from unittest.mock import MagicMock

        from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig

        config_content = """[backend1]
netapp_server_hostname = test-hostname.example.com
netapp_login = test-user
netapp_password = test-password-123
netapp_nic_slot_prefix = e5
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write(config_content)
            f.flush()

            config = NetAppConfig(f.name, "backend1")
            assert config.netapp_nic_slot_prefix == "e5"

            mock_interface_a = MagicMock()
            mock_interface_a.name = "N1-lif-A"
            mock_interface_a.address = "192.168.1.10/24"
            mock_interface_a.vlan = 100

            mock_interface_b = MagicMock()
            mock_interface_b.name = "N1-lif-B"
            mock_interface_b.address = "192.168.1.11/24"
            mock_interface_b.vlan = 100

            mock_response = MagicMock()
            mock_response.interfaces = [mock_interface_a, mock_interface_b]

            configs = NetappIPInterfaceConfig.from_nautobot_response(
                mock_response, config
            )

            assert len(configs) == 2
            assert configs[0].base_port_name == "e5a"
            assert configs[1].base_port_name == "e5b"
            assert configs[0].nic_slot_prefix == "e5"
            assert configs[1].nic_slot_prefix == "e5"

        os.unlink(f.name)
