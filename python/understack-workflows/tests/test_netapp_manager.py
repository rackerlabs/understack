import ipaddress
import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from netapp_ontap.error import NetAppRestError

from understack_workflows.netapp_manager import NetappIPInterfaceConfig
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
        mock_svm_instance.name = "os-6c2fb34446bf4b35b4f1512e51f2303d"
        mock_svm_class.return_value = mock_svm_instance

        manager = NetAppManager(mock_config_file)
        manager.create_svm("6c2fb34446bf4b35b4f1512e51f2303d", "test-aggregate")

        mock_svm_class.assert_called_once_with(
            name="os-6c2fb34446bf4b35b4f1512e51f2303d",
            aggregates=[{"name": "test-aggregate"}],
            language="c.utf_8",
            root_volume={
                "name": "os-6c2fb34446bf4b35b4f1512e51f2303d_root",
                "security_style": "unix",
            },
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
            manager.create_svm("6c2fb34446bf4b35b4f1512e51f2303d", "test-aggregate")

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
        manager.create_volume(
            "6c2fb34446bf4b35b4f1512e51f2303d", "1TB", "test-aggregate"
        )

        mock_volume_class.assert_called_once_with(
            name="vol_6c2fb34446bf4b35b4f1512e51f2303d",
            svm={"name": "os-6c2fb34446bf4b35b4f1512e51f2303d"},
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
            manager.create_volume(
                "6c2fb34446bf4b35b4f1512e51f2303d", "1TB", "test-aggregate"
            )

        assert exc_info.value.code == 1

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_svm_name(self, mock_host_connection, mock_config, mock_config_file):
        """Test SVM name generation."""
        manager = NetAppManager(mock_config_file)
        assert (
            manager._svm_name("6c2fb34446bf4b35b4f1512e51f2303d")
            == "os-6c2fb34446bf4b35b4f1512e51f2303d"
        )

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_volume_name(self, mock_host_connection, mock_config, mock_config_file):
        """Test volume name generation."""
        manager = NetAppManager(mock_config_file)
        assert (
            manager._volume_name("6c2fb34446bf4b35b4f1512e51f2303d")
            == "vol_6c2fb34446bf4b35b4f1512e51f2303d"
        )

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Svm")
    def test_delete_svm_success(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful SVM deletion."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.uuid = "test-uuid-123"
        mock_svm_class.return_value = mock_svm_instance

        manager = NetAppManager(mock_config_file)
        result = manager.delete_svm("test-svm-name")

        assert result is True
        mock_svm_instance.get.assert_called_once_with(name="test-svm-name")
        mock_svm_instance.delete.assert_called_once()

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Svm")
    def test_delete_svm_failure(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test SVM deletion failure."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.get.side_effect = Exception("SVM not found")
        mock_svm_class.return_value = mock_svm_instance

        manager = NetAppManager(mock_config_file)
        result = manager.delete_svm("nonexistent-svm")

        assert result is False

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Volume")
    def test_delete_volume_success(
        self, mock_volume_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful volume deletion."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.state = "online"
        mock_volume_class.return_value = mock_volume_instance

        manager = NetAppManager(mock_config_file)
        result = manager.delete_volume("test-volume")

        assert result is True
        mock_volume_instance.get.assert_called_once_with(name="test-volume")
        mock_volume_instance.delete.assert_called_once()

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Volume")
    def test_delete_volume_force(
        self, mock_volume_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test volume deletion with force flag."""
        mock_volume_instance = MagicMock()
        mock_volume_class.return_value = mock_volume_instance

        manager = NetAppManager(mock_config_file)
        result = manager.delete_volume("test-volume", force=True)

        assert result is True
        mock_volume_instance.delete.assert_called_once_with(
            allow_delete_while_mapped=True
        )

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Volume")
    def test_delete_volume_failure(
        self, mock_volume_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test volume deletion failure."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.get.side_effect = Exception("Volume not found")
        mock_volume_class.return_value = mock_volume_instance

        manager = NetAppManager(mock_config_file)
        result = manager.delete_volume("nonexistent-volume")

        assert result is False

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_check_if_svm_exists_true(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test check_if_svm_exists returns True when SVM exists."""
        manager = NetAppManager(mock_config_file)

        with patch.object(manager, "_svm_by_project") as mock_svm_by_project:
            mock_svm_by_project.return_value = MagicMock()
            result = manager.check_if_svm_exists("6c2fb34446bf4b35b4f1512e51f2303d")

            assert result is True
            mock_svm_by_project.assert_called_once_with(
                "6c2fb34446bf4b35b4f1512e51f2303d"
            )

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_check_if_svm_exists_false(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test check_if_svm_exists returns False when SVM doesn't exist."""
        manager = NetAppManager(mock_config_file)

        with patch.object(manager, "_svm_by_project") as mock_svm_by_project:
            mock_svm_by_project.return_value = None
            result = manager.check_if_svm_exists("6c2fb34446bf4b35b4f1512e51f2303d")

            assert result is False

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.NvmeNamespace")
    def test_mapped_namespaces(
        self, mock_nvme_namespace, mock_host_connection, mock_config, mock_config_file
    ):
        """Test mapped_namespaces method."""
        mock_collection = MagicMock()
        mock_nvme_namespace.get_collection.return_value = mock_collection

        manager = NetAppManager(mock_config_file)
        result = manager.mapped_namespaces("test-svm", "test-volume")

        assert result == mock_collection
        mock_nvme_namespace.get_collection.assert_called_once_with(
            query="svm.name=test-svm&location.volume.name=test-volume",
            fields="uuid,name,status.mapped",
        )

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_mapped_namespaces_no_connection(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test mapped_namespaces returns None when no connection."""
        manager = NetAppManager(mock_config_file)

        with patch("understack_workflows.netapp_manager.config") as mock_config_module:
            mock_config_module.CONNECTION = None
            result = manager.mapped_namespaces("test-svm", "test-volume")

            assert result is None

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_cleanup_project_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful project cleanup."""
        manager = NetAppManager(mock_config_file)

        with (
            patch.object(manager, "delete_volume") as mock_delete_vol,
            patch.object(manager, "delete_svm") as mock_delete_svm,
        ):
            mock_delete_vol.return_value = True
            mock_delete_svm.return_value = True

            result = manager.cleanup_project("6c2fb34446bf4b35b4f1512e51f2303d")

            assert result == {"volume": True, "svm": True}
            mock_delete_vol.assert_called_once_with(
                "vol_6c2fb34446bf4b35b4f1512e51f2303d"
            )
            mock_delete_svm.assert_called_once_with(
                "os-6c2fb34446bf4b35b4f1512e51f2303d"
            )

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_cleanup_project_partial_failure(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test project cleanup with partial failure."""
        manager = NetAppManager(mock_config_file)

        with (
            patch.object(manager, "delete_volume") as mock_delete_vol,
            patch.object(manager, "delete_svm") as mock_delete_svm,
        ):
            mock_delete_vol.return_value = True
            mock_delete_svm.return_value = False

            result = manager.cleanup_project("6c2fb34446bf4b35b4f1512e51f2303d")

            assert result == {"volume": True, "svm": False}

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Svm")
    def test_svm_by_project_found(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test _svm_by_project when SVM is found."""
        mock_svm_instance = MagicMock()
        mock_svm_class.find.return_value = mock_svm_instance

        manager = NetAppManager(mock_config_file)
        result = manager._svm_by_project("6c2fb34446bf4b35b4f1512e51f2303d")

        assert result == mock_svm_instance
        mock_svm_class.find.assert_called_once_with(
            name="os-6c2fb34446bf4b35b4f1512e51f2303d"
        )

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Svm")
    def test_svm_by_project_not_found(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test _svm_by_project when SVM is not found."""
        mock_svm_class.find.return_value = None

        manager = NetAppManager(mock_config_file)
        result = manager._svm_by_project("test-project-123")

        assert result is None

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Svm")
    def test_svm_by_project_netapp_error(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test _svm_by_project when NetAppRestError occurs."""
        mock_svm_class.find.side_effect = NetAppRestError("Connection error")

        manager = NetAppManager(mock_config_file)
        result = manager._svm_by_project("6c2fb34446bf4b35b4f1512e51f2303d")

        assert result is None

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.IpInterface")
    def test_create_lif_success(
        self, mock_ip_interface, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful LIF creation."""
        mock_interface_instance = MagicMock()
        mock_ip_interface.return_value = mock_interface_instance

        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        mock_port = MagicMock()
        mock_port.uuid = "port-uuid-123"

        manager = NetAppManager(mock_config_file)

        with (
            patch.object(manager, "_svm_by_project") as mock_svm_by_project,
            patch.object(manager, "create_home_port") as mock_create_port,
        ):
            mock_svm_by_project.return_value = MagicMock()
            mock_create_port.return_value = mock_port

            manager.create_lif("6c2fb34446bf4b35b4f1512e51f2303d", mock_config_obj)

            mock_interface_instance.post.assert_called_once_with(hydrate=True)

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_create_lif_svm_not_found(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test LIF creation when SVM is not found."""
        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        manager = NetAppManager(mock_config_file)

        with patch.object(manager, "_svm_by_project") as mock_svm_by_project:
            mock_svm_by_project.return_value = None

            with pytest.raises(Exception, match="SVM Not Found"):
                manager.create_lif("6c2fb34446bf4b35b4f1512e51f2303d", mock_config_obj)

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Port")
    def test_create_home_port_success(
        self, mock_port_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful home port creation."""
        mock_port_instance = MagicMock()
        mock_port_class.return_value = mock_port_instance

        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        mock_node = MagicMock()
        mock_node.name = "node-01"

        manager = NetAppManager(mock_config_file)

        with patch.object(manager, "identify_home_node") as mock_identify_node:
            mock_identify_node.return_value = mock_node

            result = manager.create_home_port(mock_config_obj)

            assert result == mock_port_instance
            mock_port_instance.post.assert_called_once_with(hydrate=True)

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    def test_create_home_port_no_node(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test home port creation when node is not found."""
        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        manager = NetAppManager(mock_config_file)

        with patch.object(manager, "identify_home_node") as mock_identify_node:
            mock_identify_node.return_value = None

            with pytest.raises(Exception, match="Could not find home node"):
                manager.create_home_port(mock_config_obj)

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Node")
    def test_identify_home_node_success(
        self, mock_node_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful node identification."""
        mock_node1 = MagicMock()
        mock_node1.name = "node-01"
        mock_node2 = MagicMock()
        mock_node2.name = "node-02"

        mock_node_class.get_collection.return_value = [mock_node1, mock_node2]

        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        manager = NetAppManager(mock_config_file)
        result = manager.identify_home_node(mock_config_obj)

        assert result == mock_node1

    @patch("understack_workflows.netapp_manager.config")
    @patch("understack_workflows.netapp_manager.HostConnection")
    @patch("understack_workflows.netapp_manager.Node")
    def test_identify_home_node_not_found(
        self, mock_node_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test node identification when no matching node found."""
        mock_node1 = MagicMock()
        mock_node1.name = "node-03"
        mock_node2 = MagicMock()
        mock_node2.name = "node-04"

        mock_node_class.get_collection.return_value = [mock_node1, mock_node2]

        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        manager = NetAppManager(mock_config_file)
        result = manager.identify_home_node(mock_config_obj)

        assert result is None


class TestNetappIPInterfaceConfig:
    """Test cases for NetappIPInterfaceConfig class."""

    def test_netmask_long(self):
        """Test netmask_long method."""
        config = NetappIPInterfaceConfig(
            name="N1-storage-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.netmask_long() == ipaddress.IPv4Address("255.255.255.0")

    def test_side_property_a(self):
        """Test side property for interface ending with A."""
        config = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.side == "A"

    def test_side_property_b(self):
        """Test side property for interface ending with B."""
        config = NetappIPInterfaceConfig(
            name="N1-test-B",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.side == "B"

    def test_side_property_invalid(self):
        """Test side property for interface with invalid ending."""
        config = NetappIPInterfaceConfig(
            name="N1-test-C",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        with pytest.raises(ValueError, match="Cannot determine side"):
            _ = config.side

    def test_desired_node_number_n1(self):
        """Test desired_node_number for N1 interface."""
        config = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.desired_node_number == 1

    def test_desired_node_number_n2(self):
        """Test desired_node_number for N2 interface."""
        config = NetappIPInterfaceConfig(
            name="N2-test-B",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.desired_node_number == 2

    def test_desired_node_number_invalid(self):
        """Test desired_node_number for invalid interface name."""
        config = NetappIPInterfaceConfig(
            name="N3-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        with pytest.raises(ValueError, match="Cannot determine node index"):
            _ = config.desired_node_number

    def test_base_port_name_a(self):
        """Test base_port_name for side A."""
        config = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.base_port_name == "e4a"

    def test_base_port_name_b(self):
        """Test base_port_name for side B."""
        config = NetappIPInterfaceConfig(
            name="N1-test-B",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.base_port_name == "e4b"

    def test_broadcast_domain_name_a(self):
        """Test broadcast_domain_name for side A."""
        config = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.broadcast_domain_name == "Fabric-A"

    def test_broadcast_domain_name_b(self):
        """Test broadcast_domain_name for side B."""
        config = NetappIPInterfaceConfig(
            name="N1-test-B",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        assert config.broadcast_domain_name == "Fabric-B"

    def test_from_nautobot_response(self):
        """Test from_nautobot_response class method."""
        # Create a mock response object
        mock_interface = MagicMock()
        mock_interface.name = "N1-test-A"
        mock_interface.address = "192.168.1.10/24"
        mock_interface.vlan = 100

        mock_response = MagicMock()
        mock_response.interfaces = [mock_interface]

        result = NetappIPInterfaceConfig.from_nautobot_response(mock_response)

        assert len(result) == 1
        config = result[0]
        assert config.name == "N1-test-A"
        assert config.address == ipaddress.IPv4Address("192.168.1.10")
        assert config.network == ipaddress.IPv4Network("192.168.1.0/24")
        assert config.vlan_id == 100
