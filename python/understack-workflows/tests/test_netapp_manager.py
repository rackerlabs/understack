import ipaddress
import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from netapp_ontap.error import NetAppRestError

from understack_workflows.netapp.manager import NetAppManager
from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig


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

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_init_success(self, mock_host_connection, mock_config, mock_config_file):
        """Test successful NetAppManager initialization."""
        NetAppManager(mock_config_file)

        mock_host_connection.assert_called_once_with(
            "test-hostname", username="test-user", password="test-password"
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    @patch("understack_workflows.netapp.manager.NetAppConfig")
    def test_init_default_config_path(
        self, mock_netapp_config, mock_host_connection, mock_config
    ):
        """Test NetAppManager initialization with default config path."""
        # Mock the NetAppConfig instance
        mock_config_instance = MagicMock()
        mock_config_instance.hostname = "default-host"
        mock_config_instance.username = "default-user"
        mock_config_instance.password = "default-pass"
        mock_netapp_config.return_value = mock_config_instance

        NetAppManager()

        mock_netapp_config.assert_called_once_with("/etc/netapp/netapp_nvme.conf")
        mock_host_connection.assert_called_once_with(
            "default-host", username="default-user", password="default-pass"
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_svm_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful SVM creation."""
        manager = NetAppManager(mock_config_file)

        # Mock the SvmService method
        manager._svm_service.create_svm = MagicMock(
            return_value="os-6c2fb34446bf4b35b4f1512e51f2303d"
        )

        result = manager.create_svm(
            "6c2fb34446bf4b35b4f1512e51f2303d", "test-aggregate"
        )

        # Verify the service was called with correct parameters
        manager._svm_service.create_svm.assert_called_once_with(
            "6c2fb34446bf4b35b4f1512e51f2303d", "test-aggregate"
        )

        # Verify the return value
        assert result == "os-6c2fb34446bf4b35b4f1512e51f2303d"

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_svm_failure(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test SVM creation failure."""
        manager = NetAppManager(mock_config_file)

        # Mock the SvmService method to raise an exception
        from understack_workflows.netapp.exceptions import NetAppManagerError

        manager._svm_service.create_svm = MagicMock(
            side_effect=NetAppManagerError("Test error")
        )

        with pytest.raises(NetAppManagerError):
            manager.create_svm("6c2fb34446bf4b35b4f1512e51f2303d", "test-aggregate")

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_volume_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful volume creation."""
        manager = NetAppManager(mock_config_file)

        # Mock the VolumeService method
        manager._volume_service.create_volume = MagicMock(
            return_value="vol_6c2fb34446bf4b35b4f1512e51f2303d"
        )

        result = manager.create_volume(
            "6c2fb34446bf4b35b4f1512e51f2303d", "1TB", "test-aggregate"
        )

        # Verify the service was called with correct parameters
        manager._volume_service.create_volume.assert_called_once_with(
            "6c2fb34446bf4b35b4f1512e51f2303d", "1TB", "test-aggregate"
        )

        # Verify the return value
        assert result == "vol_6c2fb34446bf4b35b4f1512e51f2303d"

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_volume_failure(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test volume creation failure."""
        manager = NetAppManager(mock_config_file)

        # Mock the VolumeService method to raise an exception
        from understack_workflows.netapp.exceptions import VolumeOperationError

        manager._volume_service.create_volume = MagicMock(
            side_effect=VolumeOperationError("Test error")
        )

        with pytest.raises(VolumeOperationError):
            manager.create_volume(
                "6c2fb34446bf4b35b4f1512e51f2303d", "1TB", "test-aggregate"
            )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_svm_name(self, mock_host_connection, mock_config, mock_config_file):
        """Test SVM name generation."""
        manager = NetAppManager(mock_config_file)
        assert (
            manager._svm_name("6c2fb34446bf4b35b4f1512e51f2303d")
            == "os-6c2fb34446bf4b35b4f1512e51f2303d"
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_volume_name(self, mock_host_connection, mock_config, mock_config_file):
        """Test volume name generation."""
        manager = NetAppManager(mock_config_file)
        assert (
            manager._volume_name("6c2fb34446bf4b35b4f1512e51f2303d")
            == "vol_6c2fb34446bf4b35b4f1512e51f2303d"
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_delete_svm_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful SVM deletion."""
        manager = NetAppManager(mock_config_file)

        # Mock the SvmService method for standard SVM name
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.delete_svm("os-test-project")

        assert result is True
        manager._svm_service.delete_svm.assert_called_once_with("test-project")

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_delete_svm_failure(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test SVM deletion failure."""
        manager = NetAppManager(mock_config_file)

        # Mock the client method for non-standard SVM name
        manager._client.delete_svm = MagicMock(return_value=False)

        result = manager.delete_svm("nonexistent-svm")

        assert result is False
        manager._client.delete_svm.assert_called_once_with("nonexistent-svm")

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_delete_volume_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful volume deletion."""
        manager = NetAppManager(mock_config_file)

        # Mock the VolumeService method for standard volume name
        manager._volume_service.delete_volume = MagicMock(return_value=True)

        result = manager.delete_volume("vol_test-project")

        assert result is True
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project", False
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_delete_volume_force(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test volume deletion with force flag."""
        manager = NetAppManager(mock_config_file)

        # Mock the VolumeService method for standard volume name
        manager._volume_service.delete_volume = MagicMock(return_value=True)

        result = manager.delete_volume("vol_test-project", force=True)

        assert result is True
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project", True
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_delete_volume_failure(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test volume deletion failure."""
        manager = NetAppManager(mock_config_file)

        # Mock the client method for non-standard volume name
        manager._client.delete_volume = MagicMock(return_value=False)

        result = manager.delete_volume("nonexistent-volume")

        assert result is False
        manager._client.delete_volume.assert_called_once_with(
            "nonexistent-volume", False
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_check_if_svm_exists_true(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test check_if_svm_exists returns True when SVM exists."""
        manager = NetAppManager(mock_config_file)

        # Mock the SvmService method
        manager._svm_service.exists = MagicMock(return_value=True)
        result = manager.check_if_svm_exists("6c2fb34446bf4b35b4f1512e51f2303d")

        assert result is True
        manager._svm_service.exists.assert_called_once_with(
            "6c2fb34446bf4b35b4f1512e51f2303d"
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_check_if_svm_exists_false(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test check_if_svm_exists returns False when SVM doesn't exist."""
        manager = NetAppManager(mock_config_file)

        # Mock the SvmService method
        manager._svm_service.exists = MagicMock(return_value=False)
        result = manager.check_if_svm_exists("6c2fb34446bf4b35b4f1512e51f2303d")

        assert result is False

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    @patch("understack_workflows.netapp.manager.NvmeNamespace")
    def test_mapped_namespaces(
        self, mock_nvme_namespace, mock_host_connection, mock_config, mock_config_file
    ):
        """Test mapped_namespaces method with standard naming."""
        mock_collection = MagicMock()
        mock_nvme_namespace.get_collection.return_value = mock_collection

        manager = NetAppManager(mock_config_file)

        # Mock the VolumeService method for standard names
        manager._volume_service.get_mapped_namespaces = MagicMock(
            return_value=mock_collection
        )

        result = manager.mapped_namespaces("os-test-project", "vol_test-project")

        assert result == mock_collection
        manager._volume_service.get_mapped_namespaces.assert_called_once_with(
            "test-project"
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_mapped_namespaces_no_connection(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test mapped_namespaces returns None when no connection."""
        manager = NetAppManager(mock_config_file)

        with patch("understack_workflows.netapp.manager.config") as mock_config_module:
            mock_config_module.CONNECTION = None
            result = manager.mapped_namespaces("test-svm", "test-volume")

            assert result is None

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful project cleanup."""
        manager = NetAppManager(mock_config_file)

        # Mock the service methods directly - including existence checks
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.cleanup_project("6c2fb34446bf4b35b4f1512e51f2303d")

        assert result == {"volume": True, "svm": True}
        manager._volume_service.delete_volume.assert_called_once_with(
            "6c2fb34446bf4b35b4f1512e51f2303d", force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with(
            "6c2fb34446bf4b35b4f1512e51f2303d"
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_partial_failure(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test project cleanup with partial failure."""
        manager = NetAppManager(mock_config_file)

        # Mock the service methods directly - including existence checks
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=False)

        result = manager.cleanup_project("6c2fb34446bf4b35b4f1512e51f2303d")

        assert result == {"volume": True, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    @patch("understack_workflows.netapp.manager.Svm")
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

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    @patch("understack_workflows.netapp.manager.Svm")
    def test_svm_by_project_not_found(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test _svm_by_project when SVM is not found."""
        mock_svm_class.find.return_value = None

        manager = NetAppManager(mock_config_file)
        result = manager._svm_by_project("test-project-123")

        assert result is None

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    @patch("understack_workflows.netapp.manager.Svm")
    def test_svm_by_project_netapp_error(
        self, mock_svm_class, mock_host_connection, mock_config, mock_config_file
    ):
        """Test _svm_by_project when NetAppRestError occurs."""
        mock_svm_class.find.side_effect = NetAppRestError("Connection error")

        manager = NetAppManager(mock_config_file)
        result = manager._svm_by_project("6c2fb34446bf4b35b4f1512e51f2303d")

        assert result is None

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_lif_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful LIF creation."""
        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        manager = NetAppManager(mock_config_file)

        # Mock the LifService.create_lif method since we now delegate to it
        with patch.object(manager._lif_service, "create_lif") as mock_create_lif:
            manager.create_lif("6c2fb34446bf4b35b4f1512e51f2303d", mock_config_obj)

            mock_create_lif.assert_called_once_with(
                "6c2fb34446bf4b35b4f1512e51f2303d", mock_config_obj
            )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
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

        # Mock the LifService.create_lif method to raise the expected exception
        with patch.object(manager._lif_service, "create_lif") as mock_create_lif:
            mock_create_lif.side_effect = Exception("SVM Not Found")

            with pytest.raises(Exception, match="SVM Not Found"):
                manager.create_lif("6c2fb34446bf4b35b4f1512e51f2303d", mock_config_obj)

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_home_port_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful home port creation."""
        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        mock_port_result = MagicMock()
        mock_port_result.uuid = "port-uuid-123"

        manager = NetAppManager(mock_config_file)

        # Mock the LifService.create_home_port method since we now delegate to it
        with patch.object(manager._lif_service, "create_home_port") as mock_create_port:
            mock_create_port.return_value = mock_port_result

            result = manager.create_home_port(mock_config_obj)

            assert result == mock_port_result
            mock_create_port.assert_called_once_with(mock_config_obj)

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
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

        # Mock the LifService.create_home_port method to raise the expected exception
        with patch.object(manager._lif_service, "create_home_port") as mock_create_port:
            mock_create_port.side_effect = Exception(
                "Could not find home node for N1-test-A."
            )

            with pytest.raises(Exception, match="Could not find home node"):
                manager.create_home_port(mock_config_obj)

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_identify_home_node_success(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test successful node identification."""
        mock_node1 = MagicMock()
        mock_node1.name = "node-01"

        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        manager = NetAppManager(mock_config_file)

        # Mock the LifService.identify_home_node method since we now delegate to it
        with patch.object(
            manager._lif_service, "identify_home_node"
        ) as mock_identify_node:
            mock_identify_node.return_value = mock_node1

            result = manager.identify_home_node(mock_config_obj)

            assert result == mock_node1
            mock_identify_node.assert_called_once_with(mock_config_obj)

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_identify_home_node_not_found(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test node identification when no matching node found."""
        mock_config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        manager = NetAppManager(mock_config_file)

        # Mock the LifService.identify_home_node method to return None
        with patch.object(
            manager._lif_service, "identify_home_node"
        ) as mock_identify_node:
            mock_identify_node.return_value = None

            result = manager.identify_home_node(mock_config_obj)

            assert result is None
            mock_identify_node.assert_called_once_with(mock_config_obj)


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

    def test_base_port_name_custom_prefix_a(self):
        """Test base_port_name with custom prefix for side A."""
        config = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
            nic_slot_prefix="e5",
        )

        assert config.base_port_name == "e5a"

    def test_base_port_name_custom_prefix_b(self):
        """Test base_port_name with custom prefix for side B."""
        config = NetappIPInterfaceConfig(
            name="N1-test-B",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
            nic_slot_prefix="e6",
        )

        assert config.base_port_name == "e6b"

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
