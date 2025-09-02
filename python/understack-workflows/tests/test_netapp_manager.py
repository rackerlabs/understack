"""Refactored NetApp Manager tests focusing on orchestration and delegation."""

import ipaddress
import os
import tempfile
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest

from understack_workflows.netapp.manager import NetAppManager
from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig


class TestNetAppManagerOrchestration:
    """Test NetAppManager orchestration and delegation responsibilities."""

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
    def test_initialization_with_dependency_injection(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test manager initialization sets up all required services."""
        manager = NetAppManager(mock_config_file)

        # Verify all services are initialized
        assert hasattr(manager, "_client")
        assert hasattr(manager, "_config")
        assert hasattr(manager, "_error_handler")
        assert hasattr(manager, "_svm_service")
        assert hasattr(manager, "_volume_service")
        assert hasattr(manager, "_lif_service")

        # Verify connection setup
        mock_host_connection.assert_called_once_with(
            "test-hostname", username="test-user", password="test-password"
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_svm_delegates_to_service(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test create_svm delegates to SvmService with correct parameters."""
        manager = NetAppManager(mock_config_file)
        manager._svm_service.create_svm = MagicMock(return_value="os-test-project")

        result = manager.create_svm("test-project", "test-aggregate")

        # Verify delegation with correct parameters
        manager._svm_service.create_svm.assert_called_once_with(
            "test-project", "test-aggregate"
        )
        assert result == "os-test-project"

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_volume_delegates_to_service(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test create_volume delegates to VolumeService with correct parameters."""
        manager = NetAppManager(mock_config_file)
        manager._volume_service.create_volume = MagicMock(
            return_value="vol_test-project"
        )

        result = manager.create_volume("test-project", "1TB", "test-aggregate")

        # Verify delegation with correct parameters
        manager._volume_service.create_volume.assert_called_once_with(
            "test-project", "1TB", "test-aggregate"
        )
        assert result == "vol_test-project"

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_delete_svm_standard_name_delegates_to_service(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test delete_svm with standard naming delegates to SvmService."""
        manager = NetAppManager(mock_config_file)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.delete_svm("os-test-project")

        # Verify delegation extracts project_id correctly
        manager._svm_service.delete_svm.assert_called_once_with("test-project")
        assert result is True

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_delete_svm_nonstandard_name_uses_client(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test delete_svm with non-standard naming falls back to client."""
        manager = NetAppManager(mock_config_file)
        manager._client.delete_svm = MagicMock(return_value=True)

        result = manager.delete_svm("custom-svm-name")

        # Verify fallback to client for non-standard names
        manager._client.delete_svm.assert_called_once_with("custom-svm-name")
        assert result is True

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_delete_volume_standard_name_delegates_to_service(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test delete_volume with standard naming delegates to VolumeService."""
        manager = NetAppManager(mock_config_file)
        manager._volume_service.delete_volume = MagicMock(return_value=True)

        result = manager.delete_volume("vol_test-project", force=True)

        # Verify delegation extracts project_id correctly
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project", True
        )
        assert result is True

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_check_if_svm_exists_delegates_to_service(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test check_if_svm_exists delegates to SvmService."""
        manager = NetAppManager(mock_config_file)
        manager._svm_service.exists = MagicMock(return_value=True)

        result = manager.check_if_svm_exists("test-project")

        manager._svm_service.exists.assert_called_once_with("test-project")
        assert result is True

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_mapped_namespaces_standard_names_delegates_to_service(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test mapped_namespaces with standard naming delegates to VolumeService."""
        manager = NetAppManager(mock_config_file)
        expected_namespaces = ["namespace1", "namespace2"]
        manager._volume_service.get_mapped_namespaces = MagicMock(
            return_value=expected_namespaces
        )

        result = manager.mapped_namespaces("os-test-project", "vol_test-project")

        # Verify delegation with extracted project_id
        manager._volume_service.get_mapped_namespaces.assert_called_once_with(
            "test-project"
        )
        assert result == expected_namespaces

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_lif_delegates_to_service(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test create_lif delegates to LifService."""
        manager = NetAppManager(mock_config_file)
        manager._lif_service.create_lif = MagicMock()

        config_obj = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

        manager.create_lif("test-project", config_obj)

        manager._lif_service.create_lif.assert_called_once_with(
            "test-project", config_obj
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_naming_convention_utilities(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test naming convention utility methods."""
        manager = NetAppManager(mock_config_file)

        # Test SVM naming
        assert manager._svm_name("test-project") == "os-test-project"

        # Test volume naming
        assert manager._volume_name("test-project") == "vol_test-project"

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_error_propagation_from_services(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that errors from services are properly propagated."""
        manager = NetAppManager(mock_config_file)

        # Test SVM service error propagation
        from understack_workflows.netapp.exceptions import SvmOperationError

        manager._svm_service.create_svm = MagicMock(
            side_effect=SvmOperationError("SVM creation failed")
        )

        with pytest.raises(SvmOperationError, match="SVM creation failed"):
            manager.create_svm("test-project", "test-aggregate")

        # Test Volume service error propagation
        from understack_workflows.netapp.exceptions import VolumeOperationError

        manager._volume_service.create_volume = MagicMock(
            side_effect=VolumeOperationError("Volume creation failed")
        )

        with pytest.raises(VolumeOperationError, match="Volume creation failed"):
            manager.create_volume("test-project", "1TB", "test-aggregate")

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_orchestration(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup_project orchestrates services correctly."""
        manager = NetAppManager(mock_config_file)

        # Mock service methods
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=True)
        manager._svm_service.delete_svm = MagicMock(return_value=True)

        result = manager.cleanup_project("test-project")

        # Verify orchestration sequence
        manager._volume_service.exists.assert_called_once_with("test-project")
        manager._svm_service.exists.assert_called_once_with("test-project")
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project", force=True
        )
        manager._svm_service.delete_svm.assert_called_once_with("test-project")

        assert result == {"volume": True, "svm": True}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_cleanup_project_volume_failure_stops_svm_deletion(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test cleanup_project stops SVM deletion when volume deletion fails."""
        manager = NetAppManager(mock_config_file)

        # Mock volume deletion failure
        manager._volume_service.exists = MagicMock(return_value=True)
        manager._svm_service.exists = MagicMock(return_value=True)
        manager._volume_service.delete_volume = MagicMock(return_value=False)
        manager._svm_service.delete_svm = MagicMock()

        result = manager.cleanup_project("test-project")

        # Verify SVM deletion was not attempted
        manager._volume_service.delete_volume.assert_called_once_with(
            "test-project", force=True
        )
        manager._svm_service.delete_svm.assert_not_called()

        assert result == {"volume": False, "svm": False}

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_public_api_contract_maintained(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that all public method signatures are maintained."""
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

        # Test all public methods can be called with expected signatures
        try:
            manager.create_svm("project", "aggregate")
            manager.delete_svm("svm-name")
            manager.create_volume("project", "1TB", "aggregate")
            manager.delete_volume("volume-name")
            manager.delete_volume("volume-name", force=True)
            manager.check_if_svm_exists("project")
            manager.mapped_namespaces("svm", "volume")
            manager.cleanup_project("project")

            # Network-related methods
            config_obj = NetappIPInterfaceConfig(
                name="test",
                address=ipaddress.IPv4Address("192.168.1.1"),
                network=ipaddress.IPv4Network("192.168.1.0/24"),
                vlan_id=100,
            )
            manager.create_lif("project", config_obj)
            manager.create_home_port(config_obj)
            manager.identify_home_node(config_obj)

        except TypeError as e:
            pytest.fail(f"Public API contract broken: {e}")


class TestNetAppManagerValueObjects:
    """Test NetappIPInterfaceConfig value object (kept for backward compatibility)."""

    def test_netmask_long(self):
        """Test netmask_long method."""
        config = NetappIPInterfaceConfig(
            name="N1-storage-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )
        assert config.netmask_long() == ipaddress.IPv4Address("255.255.255.0")

    def test_side_property_extraction(self):
        """Test side property extraction from interface names."""
        config_a = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )
        assert config_a.side == "A"

        config_b = NetappIPInterfaceConfig(
            name="N1-test-B",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )
        assert config_b.side == "B"

    def test_desired_node_number_extraction(self):
        """Test node number extraction from interface names."""
        config_n1 = NetappIPInterfaceConfig(
            name="N1-test-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )
        assert config_n1.desired_node_number == 1

        config_n2 = NetappIPInterfaceConfig(
            name="N2-test-B",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )
        assert config_n2.desired_node_number == 2


class TestNetAppManagerRouteIntegration:
    """Test NetAppManager route integration functionality."""

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

    @pytest.fixture
    def sample_interface_configs(self):
        """Create sample interface configurations for testing."""
        return [
            NetappIPInterfaceConfig(
                name="N1-lif-A",
                address=ipaddress.IPv4Address("100.127.0.21"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            ),
            NetappIPInterfaceConfig(
                name="N1-lif-B",
                address=ipaddress.IPv4Address("100.127.128.21"),
                network=ipaddress.IPv4Network("100.127.128.16/29"),
                vlan_id=200,
            ),
            NetappIPInterfaceConfig(
                name="N2-lif-A",
                address=ipaddress.IPv4Address("100.127.0.22"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            ),
        ]

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_route_service_initialization(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test that RouteService is properly initialized in NetAppManager."""
        manager = NetAppManager(mock_config_file)

        # Verify route service is initialized
        assert hasattr(manager, "_route_service")
        assert manager._route_service is not None

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_routes_for_project_delegates_to_service(
        self,
        mock_host_connection,
        mock_config,
        mock_config_file,
        sample_interface_configs,
    ):
        """Test create_routes_for_project delegates to RouteService."""
        from understack_workflows.netapp.value_objects import RouteResult

        manager = NetAppManager(mock_config_file)

        # Mock route service
        expected_results = [
            RouteResult(
                uuid="route-uuid-1",
                gateway="100.127.0.17",
                destination="100.126.0.0/17",
                svm_name="os-test-project",
            ),
            RouteResult(
                uuid="route-uuid-2",
                gateway="100.127.128.17",
                destination="100.126.128.0/17",
                svm_name="os-test-project",
            ),
        ]
        manager._route_service.create_routes_from_interfaces = MagicMock(
            return_value=expected_results
        )

        result = manager.create_routes_for_project(
            "test-project", sample_interface_configs
        )

        # Verify delegation with correct parameters
        manager._route_service.create_routes_from_interfaces.assert_called_once_with(
            "test-project", sample_interface_configs
        )
        assert result == expected_results

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_routes_for_project_error_handling(
        self,
        mock_host_connection,
        mock_config,
        mock_config_file,
        sample_interface_configs,
    ):
        """Test create_routes_for_project error handling and propagation."""
        from understack_workflows.netapp.exceptions import NetworkOperationError

        manager = NetAppManager(mock_config_file)

        # Mock route service to raise an error
        manager._route_service.create_routes_from_interfaces = MagicMock(
            side_effect=NetworkOperationError("Route creation failed")
        )

        # Verify error is propagated
        with pytest.raises(NetworkOperationError, match="Route creation failed"):
            manager.create_routes_for_project("test-project", sample_interface_configs)

        # Verify service was called
        manager._route_service.create_routes_from_interfaces.assert_called_once_with(
            "test-project", sample_interface_configs
        )

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_routes_for_project_logging(
        self,
        mock_host_connection,
        mock_config,
        mock_config_file,
        sample_interface_configs,
    ):
        """Test create_routes_for_project logging behavior."""
        from understack_workflows.netapp.value_objects import RouteResult

        manager = NetAppManager(mock_config_file)

        # Mock route service
        expected_results = [
            RouteResult(
                uuid="route-uuid-1",
                gateway="100.127.0.17",
                destination="100.126.0.0/17",
                svm_name="os-test-project",
            ),
        ]
        manager._route_service.create_routes_from_interfaces = MagicMock(
            return_value=expected_results
        )

        with patch("understack_workflows.netapp.manager.logger") as mock_logger:
            result = manager.create_routes_for_project(
                "test-project", sample_interface_configs
            )

            # Verify logging calls
            mock_logger.info.assert_any_call(
                "Creating routes for project %(project_id)s with %(count)d interfaces",
                {"project_id": "test-project", "count": 3},
            )
            mock_logger.info.assert_any_call(
                "Successfully created %(count)d routes for project %(project_id)s",
                {"count": 1, "project_id": "test-project"},
            )

        assert result == expected_results

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_create_routes_for_project_empty_interfaces(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test create_routes_for_project with empty interface list."""
        manager = NetAppManager(mock_config_file)

        # Mock route service
        manager._route_service.create_routes_from_interfaces = MagicMock(
            return_value=[]
        )

        result = manager.create_routes_for_project("test-project", [])

        # Verify delegation with empty list
        manager._route_service.create_routes_from_interfaces.assert_called_once_with(
            "test-project", []
        )
        assert result == []

    @patch("understack_workflows.netapp.manager.config")
    @patch("understack_workflows.netapp.manager.HostConnection")
    def test_route_service_dependency_injection(
        self, mock_host_connection, mock_config, mock_config_file
    ):
        """Test NetAppManager with injected RouteService dependency."""
        from understack_workflows.netapp.route_service import RouteService

        # Create mock dependencies
        mock_client = MagicMock()
        mock_error_handler = MagicMock()
        mock_route_service = MagicMock(spec=RouteService)

        manager = NetAppManager(
            config_path=mock_config_file,
            netapp_client=mock_client,
            route_service=mock_route_service,
            error_handler=mock_error_handler,
        )

        # Verify injected route service is used
        assert manager._route_service is mock_route_service

        # Test delegation works with injected service
        mock_route_service.create_routes_from_interfaces.return_value = []
        result = manager.create_routes_for_project("test-project", [])

        mock_route_service.create_routes_from_interfaces.assert_called_once_with(
            "test-project", []
        )
        assert result == []
