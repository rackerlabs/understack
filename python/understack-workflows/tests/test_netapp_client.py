"""Tests for NetAppClient abstraction layer."""

import ipaddress
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from netapp_ontap.error import NetAppRestError

from understack_workflows.netapp.client import NetAppClient
from understack_workflows.netapp.client import NetAppClientInterface
from understack_workflows.netapp.config import NetAppConfig
from understack_workflows.netapp.error_handler import ErrorHandler
from understack_workflows.netapp.exceptions import NetworkOperationError
from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError
from understack_workflows.netapp.value_objects import InterfaceResult
from understack_workflows.netapp.value_objects import InterfaceSpec
from understack_workflows.netapp.value_objects import NamespaceResult
from understack_workflows.netapp.value_objects import NamespaceSpec
from understack_workflows.netapp.value_objects import NodeResult
from understack_workflows.netapp.value_objects import PortResult
from understack_workflows.netapp.value_objects import PortSpec
from understack_workflows.netapp.value_objects import RouteSpec
from understack_workflows.netapp.value_objects import SvmResult
from understack_workflows.netapp.value_objects import SvmSpec
from understack_workflows.netapp.value_objects import VolumeResult
from understack_workflows.netapp.value_objects import VolumeSpec


class TestNetAppClient:
    """Test cases for NetAppClient class."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock NetApp configuration."""
        config = Mock(spec=NetAppConfig)
        config.hostname = "test-netapp.example.com"
        config.username = "test-user"
        config.password = "test-password"
        config.config_path = "/test/config/path"
        return config

    @pytest.fixture
    def mock_error_handler(self):
        """Create a mock error handler."""
        return Mock(spec=ErrorHandler)

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        return Mock()

    @pytest.fixture
    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.HostConnection")
    def netapp_client(
        self, mock_host_connection, mock_config_module, mock_config, mock_error_handler
    ):
        """Create a NetAppClient instance with mocked dependencies."""
        return NetAppClient(mock_config, mock_error_handler)

    def test_implements_interface(self, netapp_client):
        """Test that NetAppClient implements the NetAppClientInterface."""
        assert isinstance(netapp_client, NetAppClientInterface)

    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.HostConnection")
    def test_init_success(
        self, mock_host_connection, mock_config_module, mock_config, mock_error_handler
    ):
        """Test successful NetAppClient initialization."""
        # Ensure no existing connection
        mock_config_module.CONNECTION = None

        NetAppClient(mock_config, mock_error_handler)

        mock_host_connection.assert_called_once_with(
            "test-netapp.example.com", username="test-user", password="test-password"
        )
        mock_error_handler.log_info.assert_called_once()

    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.HostConnection")
    def test_init_connection_failure(
        self, mock_host_connection, mock_config_module, mock_config, mock_error_handler
    ):
        """Test NetApp Client initialization with connection failure."""
        # Ensure no existing connection
        mock_config_module.CONNECTION = None
        mock_host_connection.side_effect = Exception("Connection failed")

        NetAppClient(mock_config, mock_error_handler)

        mock_error_handler.handle_config_error.assert_called_once()

    @patch("understack_workflows.netapp.client.Svm")
    def test_create_svm_success(self, mock_svm_class, netapp_client):
        """Test successful SVM creation."""
        # Setup mock SVM instance
        mock_svm_instance = MagicMock()
        mock_svm_instance.name = "test-svm"
        mock_svm_instance.uuid = "svm-uuid-123"
        mock_svm_instance.state = "online"
        mock_svm_class.return_value = mock_svm_instance

        # Create SVM spec
        svm_spec = SvmSpec(name="test-svm", aggregate_name="test-aggregate")

        # Execute
        result = netapp_client.create_svm(svm_spec)

        # Verify
        assert isinstance(result, SvmResult)
        assert result.name == "test-svm"
        assert result.uuid == "svm-uuid-123"
        assert result.state == "online"

        mock_svm_class.assert_called_once_with(
            name="test-svm",
            aggregates=[{"name": "test-aggregate"}],
            language="c.utf_8",
            root_volume={"name": "test-svm_root", "security_style": "unix"},
            allowed_protocols=["nvme"],
            nvme={"enabled": True},
        )
        mock_svm_instance.post.assert_called_once()
        mock_svm_instance.get.assert_called_once()

    @patch("understack_workflows.netapp.client.Svm")
    def test_create_svm_failure(self, mock_svm_class, netapp_client):
        """Test SVM creation failure."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.post.side_effect = NetAppRestError("SVM creation failed")
        mock_svm_class.return_value = mock_svm_instance

        # Configure mock error handler to raise the expected exception
        netapp_client._error_handler.handle_netapp_error.side_effect = (
            SvmOperationError(
                "NetApp SVM creation failed: SVM creation failed", svm_name="test-svm"
            )
        )

        svm_spec = SvmSpec(name="test-svm", aggregate_name="test-aggregate")

        with pytest.raises(SvmOperationError):
            netapp_client.create_svm(svm_spec)

        netapp_client._error_handler.handle_netapp_error.assert_called_once()

    @patch("understack_workflows.netapp.client.Svm")
    def test_delete_svm_success(self, mock_svm_class, netapp_client):
        """Test successful SVM deletion."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.uuid = "svm-uuid-123"
        mock_svm_class.return_value = mock_svm_instance

        result = netapp_client.delete_svm("test-svm")

        assert result is True
        mock_svm_instance.get.assert_called_once_with(name="test-svm")
        mock_svm_instance.delete.assert_called_once()

    @patch("understack_workflows.netapp.client.Svm")
    def test_delete_svm_failure(self, mock_svm_class, netapp_client):
        """Test SVM deletion failure."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.get.side_effect = Exception("SVM not found")
        mock_svm_class.return_value = mock_svm_instance

        result = netapp_client.delete_svm("nonexistent-svm")

        assert result is False
        netapp_client._error_handler.log_warning.assert_called()

    @patch("understack_workflows.netapp.client.Svm")
    def test_find_svm_found(self, mock_svm_class, netapp_client):
        """Test finding an existing SVM."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.name = "test-svm"
        mock_svm_instance.uuid = "svm-uuid-123"
        mock_svm_instance.state = "online"
        mock_svm_class.find.return_value = mock_svm_instance

        result = netapp_client.find_svm("test-svm")

        assert isinstance(result, SvmResult)
        assert result.name == "test-svm"
        assert result.uuid == "svm-uuid-123"
        assert result.state == "online"

    @patch("understack_workflows.netapp.client.Svm")
    def test_find_svm_not_found(self, mock_svm_class, netapp_client):
        """Test finding a non-existent SVM."""
        mock_svm_class.find.return_value = None

        result = netapp_client.find_svm("nonexistent-svm")

        assert result is None

    @patch("understack_workflows.netapp.client.Svm")
    def test_find_svm_netapp_error(self, mock_svm_class, netapp_client):
        """Test finding SVM with NetApp error."""
        mock_svm_class.find.side_effect = NetAppRestError("Connection error")

        result = netapp_client.find_svm("test-svm")

        assert result is None

    @patch("understack_workflows.netapp.client.Volume")
    def test_create_volume_success(self, mock_volume_class, netapp_client):
        """Test successful volume creation."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.name = "test-volume"
        mock_volume_instance.uuid = "volume-uuid-123"
        mock_volume_instance.size = "1TB"
        mock_volume_instance.state = "online"
        mock_volume_class.return_value = mock_volume_instance

        volume_spec = VolumeSpec(
            name="test-volume",
            svm_name="test-svm",
            aggregate_name="test-aggregate",
            size="1TB",
        )

        result = netapp_client.create_volume(volume_spec)

        assert isinstance(result, VolumeResult)
        assert result.name == "test-volume"
        assert result.uuid == "volume-uuid-123"
        assert result.size == "1TB"
        assert result.state == "online"
        assert result.svm_name == "test-svm"

        mock_volume_class.assert_called_once_with(
            name="test-volume",
            svm={"name": "test-svm"},
            aggregates=[{"name": "test-aggregate"}],
            size="1TB",
        )

    @patch("understack_workflows.netapp.client.Volume")
    def test_create_volume_failure(self, mock_volume_class, netapp_client):
        """Test volume creation failure."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.post.side_effect = NetAppRestError(
            "Volume creation failed"
        )
        mock_volume_class.return_value = mock_volume_instance

        # Configure mock error handler to raise the expected exception
        netapp_client._error_handler.handle_netapp_error.side_effect = (
            VolumeOperationError(
                "NetApp Volume creation failed: Volume creation failed",
                volume_name="test-volume",
            )
        )

        volume_spec = VolumeSpec(
            name="test-volume",
            svm_name="test-svm",
            aggregate_name="test-aggregate",
            size="1TB",
        )

        with pytest.raises(VolumeOperationError):
            netapp_client.create_volume(volume_spec)

    @patch("understack_workflows.netapp.client.Volume")
    def test_delete_volume_success(self, mock_volume_class, netapp_client):
        """Test successful volume deletion."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.state = "online"
        mock_volume_class.return_value = mock_volume_instance

        result = netapp_client.delete_volume("test-volume")

        assert result is True
        mock_volume_instance.get.assert_called_once_with(name="test-volume")
        mock_volume_instance.delete.assert_called_once()

    @patch("understack_workflows.netapp.client.Volume")
    def test_delete_volume_force(self, mock_volume_class, netapp_client):
        """Test volume deletion with force flag."""
        mock_volume_instance = MagicMock()
        mock_volume_class.return_value = mock_volume_instance

        result = netapp_client.delete_volume("test-volume", force=True)

        assert result is True
        mock_volume_instance.delete.assert_called_once_with(
            allow_delete_while_mapped=True
        )

    @patch("understack_workflows.netapp.client.Volume")
    def test_delete_volume_failure(self, mock_volume_class, netapp_client):
        """Test volume deletion failure."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.get.side_effect = Exception("Volume not found")
        mock_volume_class.return_value = mock_volume_instance

        result = netapp_client.delete_volume("nonexistent-volume")

        assert result is False

    @patch("understack_workflows.netapp.client.IpInterface")
    def test_create_ip_interface_success(self, mock_interface_class, netapp_client):
        """Test successful IP interface creation."""
        mock_interface_instance = MagicMock()
        mock_interface_instance.name = "test-interface"
        mock_interface_instance.uuid = "interface-uuid-123"
        mock_interface_class.return_value = mock_interface_instance

        interface_spec = InterfaceSpec(
            name="test-interface",
            address="192.168.1.10",
            netmask="255.255.255.0",
            svm_name="test-svm",
            home_port_uuid="port-uuid-123",
            broadcast_domain_name="test-domain",
        )

        result = netapp_client.create_ip_interface(interface_spec)

        assert isinstance(result, InterfaceResult)
        assert result.name == "test-interface"
        assert result.uuid == "interface-uuid-123"
        assert result.address == "192.168.1.10"
        assert result.netmask == "255.255.255.0"
        assert result.enabled is True
        assert result.svm_name == "test-svm"

        mock_interface_instance.post.assert_called_once_with(hydrate=True)

    @patch("understack_workflows.netapp.client.IpInterface")
    def test_create_ip_interface_failure(self, mock_interface_class, netapp_client):
        """Test IP interface creation failure."""
        mock_interface_instance = MagicMock()
        mock_interface_instance.post.side_effect = NetAppRestError(
            "Interface creation failed"
        )
        mock_interface_class.return_value = mock_interface_instance

        # Configure mock error handler to raise the expected exception
        netapp_client._error_handler.handle_netapp_error.side_effect = (
            NetworkOperationError(
                "NetApp IP interface creation failed: Interface creation failed",
                interface_name="test-interface",
            )
        )

        interface_spec = InterfaceSpec(
            name="test-interface",
            address="192.168.1.10",
            netmask="255.255.255.0",
            svm_name="test-svm",
            home_port_uuid="port-uuid-123",
            broadcast_domain_name="test-domain",
        )

        with pytest.raises(NetworkOperationError):
            netapp_client.create_ip_interface(interface_spec)

    @patch("understack_workflows.netapp.client.Port")
    def test_create_port_success(self, mock_port_class, netapp_client):
        """Test successful port creation."""
        mock_port_instance = MagicMock()
        mock_port_instance.uuid = "port-uuid-123"
        mock_port_instance.name = "e4a-100"
        mock_port_class.return_value = mock_port_instance

        port_spec = PortSpec(
            node_name="node-01",
            vlan_id=100,
            base_port_name="e4a",
            broadcast_domain_name="test-domain",
        )

        result = netapp_client.create_port(port_spec)

        assert isinstance(result, PortResult)
        assert result.uuid == "port-uuid-123"
        assert result.name == "e4a-100"
        assert result.node_name == "node-01"
        assert result.port_type == "vlan"

        mock_port_instance.post.assert_called_once_with(hydrate=True)

    @patch("understack_workflows.netapp.client.Port")
    def test_create_port_failure(self, mock_port_class, netapp_client):
        """Test port creation failure."""
        mock_port_instance = MagicMock()
        mock_port_instance.post.side_effect = NetAppRestError("Port creation failed")
        mock_port_class.return_value = mock_port_instance

        # Configure mock error handler to raise the expected exception
        netapp_client._error_handler.handle_netapp_error.side_effect = (
            NetworkOperationError("NetApp Port creation failed: Port creation failed")
        )

        port_spec = PortSpec(
            node_name="node-01",
            vlan_id=100,
            base_port_name="e4a",
            broadcast_domain_name="test-domain",
        )

        with pytest.raises(NetworkOperationError):
            netapp_client.create_port(port_spec)

    @patch("understack_workflows.netapp.client.Node")
    def test_get_nodes_success(self, mock_node_class, netapp_client):
        """Test successful node retrieval."""
        mock_node1 = MagicMock()
        mock_node1.name = "node-01"
        mock_node1.uuid = "node-uuid-1"

        mock_node2 = MagicMock()
        mock_node2.name = "node-02"
        mock_node2.uuid = "node-uuid-2"

        mock_node_class.get_collection.return_value = [mock_node1, mock_node2]

        result = netapp_client.get_nodes()

        assert len(result) == 2
        assert all(isinstance(node, NodeResult) for node in result)
        assert result[0].name == "node-01"
        assert result[0].uuid == "node-uuid-1"
        assert result[1].name == "node-02"
        assert result[1].uuid == "node-uuid-2"

    @patch("understack_workflows.netapp.client.Node")
    def test_get_nodes_failure(self, mock_node_class, netapp_client):
        """Test node retrieval failure."""
        mock_node_class.get_collection.side_effect = NetAppRestError(
            "Node retrieval failed"
        )

        # Configure mock error handler to raise the expected exception
        from understack_workflows.netapp.exceptions import NetAppManagerError

        netapp_client._error_handler.handle_netapp_error.side_effect = (
            NetAppManagerError("NetApp Node retrieval failed: Node retrieval failed")
        )

        with pytest.raises(NetAppManagerError):
            netapp_client.get_nodes()

    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.NvmeNamespace")
    def test_get_namespaces_success(
        self, mock_namespace_class, mock_config_module, netapp_client
    ):
        """Test successful namespace retrieval."""
        # Setup connection
        mock_config_module.CONNECTION = MagicMock()

        # Setup mock namespaces
        mock_ns1 = MagicMock()
        mock_ns1.uuid = "ns-uuid-1"
        mock_ns1.name = "namespace-1"
        mock_ns1.status.mapped = True

        mock_ns2 = MagicMock()
        mock_ns2.uuid = "ns-uuid-2"
        mock_ns2.name = "namespace-2"
        mock_ns2.status.mapped = False

        mock_namespace_class.get_collection.return_value = [mock_ns1, mock_ns2]

        namespace_spec = NamespaceSpec(svm_name="test-svm", volume_name="test-volume")

        result = netapp_client.get_namespaces(namespace_spec)

        assert len(result) == 2
        assert all(isinstance(ns, NamespaceResult) for ns in result)
        assert result[0].uuid == "ns-uuid-1"
        assert result[0].name == "namespace-1"
        assert result[0].mapped is True
        assert result[0].svm_name == "test-svm"
        assert result[0].volume_name == "test-volume"

        mock_namespace_class.get_collection.assert_called_once_with(
            query="svm.name=test-svm&location.volume.name=test-volume",
            fields="uuid,name,status.mapped",
        )

    @patch("understack_workflows.netapp.client.config")
    def test_get_namespaces_no_connection(self, mock_config_module, netapp_client):
        """Test namespace retrieval with no connection."""
        mock_config_module.CONNECTION = None

        namespace_spec = NamespaceSpec(svm_name="test-svm", volume_name="test-volume")

        result = netapp_client.get_namespaces(namespace_spec)

        assert result == []
        netapp_client._error_handler.log_warning.assert_called_once()

    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.NvmeNamespace")
    def test_get_namespaces_failure(
        self, mock_namespace_class, mock_config_module, netapp_client
    ):
        """Test namespace retrieval failure."""
        mock_config_module.CONNECTION = MagicMock()
        mock_namespace_class.get_collection.side_effect = NetAppRestError(
            "Namespace query failed"
        )

        # Configure mock error handler to raise the expected exception
        from understack_workflows.netapp.exceptions import NetAppManagerError

        netapp_client._error_handler.handle_netapp_error.side_effect = (
            NetAppManagerError("NetApp Namespace query failed: Namespace query failed")
        )

        namespace_spec = NamespaceSpec(svm_name="test-svm", volume_name="test-volume")

        with pytest.raises(NetAppManagerError):
            netapp_client.get_namespaces(namespace_spec)

    @patch("understack_workflows.netapp.client.NetworkRoute")
    def test_create_route_success(self, mock_route_class, netapp_client):
        """Test successful route creation."""
        mock_route_instance = MagicMock()
        mock_route_instance.uuid = "route-uuid-123"
        mock_route_class.return_value = mock_route_instance

        route_spec = RouteSpec(
            svm_name="os-test-project",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
        )

        result = netapp_client.create_route(route_spec)

        # Verify route configuration
        assert mock_route_instance.svm == {"name": "os-test-project"}
        assert mock_route_instance.gateway == "100.127.0.17"
        assert mock_route_instance.destination == {
            "address": "100.126.0.0",
            "netmask": "255.255.128.0",
        }
        mock_route_instance.post.assert_called_once_with(hydrate=True)

        # Verify result
        assert result.uuid == "route-uuid-123"
        assert result.gateway == "100.127.0.17"
        assert result.destination == ipaddress.IPv4Network("100.126.0.0/17")
        assert result.svm_name == "os-test-project"

    @patch("understack_workflows.netapp.client.NetworkRoute")
    def test_create_route_netapp_rest_error(self, mock_route_class, netapp_client):
        """Test route creation with NetAppRestError."""
        mock_route_instance = MagicMock()
        mock_route_instance.post.side_effect = NetAppRestError("SVM not found")
        mock_route_class.return_value = mock_route_instance

        # Configure error handler to raise NetworkOperationError
        netapp_client._error_handler.handle_netapp_error.side_effect = (
            NetworkOperationError(
                "Route creation failed: SVM not found",
                interface_name="test-route",
                context={"svm_name": "os-nonexistent-project"},
            )
        )

        route_spec = RouteSpec(
            svm_name="os-nonexistent-project",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
        )

        with pytest.raises(NetworkOperationError):
            netapp_client.create_route(route_spec)

        # Verify error handler was called with correct context
        netapp_client._error_handler.handle_netapp_error.assert_called_once()
        call_args = netapp_client._error_handler.handle_netapp_error.call_args
        assert isinstance(call_args[0][0], NetAppRestError)
        assert call_args[0][1] == "Route creation"
        assert call_args[0][2]["svm_name"] == "os-nonexistent-project"
        assert call_args[0][2]["gateway"] == "100.127.0.17"
        assert call_args[0][2]["destination"] == ipaddress.IPv4Network("100.126.0.0/17")

    @patch("understack_workflows.netapp.client.NetworkRoute")
    def test_create_route_invalid_svm_error(self, mock_route_class, netapp_client):
        """Test route creation with invalid SVM name."""
        mock_route_instance = MagicMock()
        mock_route_instance.post.side_effect = NetAppRestError(
            "SVM 'os-invalid-svm' does not exist"
        )
        mock_route_class.return_value = mock_route_instance

        # Configure error handler to raise NetworkOperationError
        netapp_client._error_handler.handle_netapp_error.side_effect = (
            NetworkOperationError(
                "Route creation failed: SVM does not exist",
                interface_name="test-route",
                context={"svm_name": "os-invalid-svm"},
            )
        )

        route_spec = RouteSpec(
            svm_name="os-invalid-svm",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
        )

        with pytest.raises(NetworkOperationError):
            netapp_client.create_route(route_spec)

        # Verify error context includes SVM information
        call_args = netapp_client._error_handler.handle_netapp_error.call_args
        assert call_args[0][2]["svm_name"] == "os-invalid-svm"

    @patch("understack_workflows.netapp.client.NetworkRoute")
    def test_create_route_gateway_unreachable_error(
        self, mock_route_class, netapp_client
    ):
        """Test route creation with unreachable gateway."""
        mock_route_instance = MagicMock()
        mock_route_instance.post.side_effect = NetAppRestError(
            "Gateway 192.168.1.1 is not reachable from SVM network"
        )
        mock_route_class.return_value = mock_route_instance

        # Configure error handler to raise NetworkOperationError
        netapp_client._error_handler.handle_netapp_error.side_effect = (
            NetworkOperationError(
                "Route creation failed: Gateway unreachable",
                interface_name="test-route",
                context={"gateway": "192.168.1.1"},
            )
        )

        route_spec = RouteSpec(
            svm_name="os-test-project",
            gateway="192.168.1.1",  # Invalid gateway for this network
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
        )

        with pytest.raises(NetworkOperationError):
            netapp_client.create_route(route_spec)

        # Verify error context includes gateway information
        call_args = netapp_client._error_handler.handle_netapp_error.call_args
        assert call_args[0][2]["gateway"] == "192.168.1.1"
        assert call_args[0][2]["destination"] == ipaddress.IPv4Network("100.126.0.0/17")

    @patch("understack_workflows.netapp.client.NetworkRoute")
    def test_create_route_logging_behavior(self, mock_route_class, netapp_client):
        """Test route creation logging behavior."""
        mock_route_instance = MagicMock()
        mock_route_instance.uuid = "route-uuid-456"
        mock_route_class.return_value = mock_route_instance

        route_spec = RouteSpec(
            svm_name="os-logging-test",
            gateway="100.127.128.17",
            destination=ipaddress.IPv4Network("100.126.128.0/17"),
        )

        netapp_client.create_route(route_spec)

        # Verify logging calls
        error_handler = netapp_client._error_handler
        log_info_calls = error_handler.log_info.call_args_list
        log_debug_calls = error_handler.log_debug.call_args_list

        # Should have info logs for start and completion
        assert len(log_info_calls) >= 2

        # Should have debug log for route creation
        assert len(log_debug_calls) >= 1

        # Find the route-specific log messages
        route_start_logs = [
            call for call in log_info_calls if "Creating route:" in call[0][0]
        ]
        route_completion_logs = [
            call
            for call in log_info_calls
            if "Route created successfully:" in call[0][0]
        ]

        # Verify route start log
        assert len(route_start_logs) == 1
        start_log = route_start_logs[0]
        assert start_log[0][1]["destination"] == ipaddress.IPv4Network(
            "100.126.128.0/17"
        )
        assert start_log[0][1]["gateway"] == "100.127.128.17"
        assert start_log[0][1]["svm_name"] == "os-logging-test"

        # Verify route completion log
        assert len(route_completion_logs) == 1
        completion_log = route_completion_logs[0]
        assert completion_log[0][1]["uuid"] == "route-uuid-456"


class TestNetAppClientInterface:
    """Test cases for NetAppClientInterface abstract class."""

    def test_interface_is_abstract(self):
        """Test that NetAppClientInterface cannot be instantiated directly."""
        with pytest.raises(TypeError):
            NetAppClientInterface()  # type: ignore[abstract]

    def test_interface_methods_are_abstract(self):
        """Test that all interface methods are abstract."""
        abstract_methods = NetAppClientInterface.__abstractmethods__
        expected_methods = {
            "create_svm",
            "delete_svm",
            "find_svm",
            "create_volume",
            "delete_volume",
            "find_volume",
            "create_ip_interface",
            "create_port",
            "get_nodes",
            "get_namespaces",
            "create_route",
        }
        assert abstract_methods == expected_methods
