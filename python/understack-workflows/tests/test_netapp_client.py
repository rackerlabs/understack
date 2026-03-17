"""Tests for NetAppClient abstraction layer."""

import ipaddress
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests
from netapp_ontap.error import NetAppRestError
from pydantic import ValidationError

from understack_workflows.netapp.client import NetAppClient
from understack_workflows.netapp.client import NetAppClientInterface
from understack_workflows.netapp.config import NetAppConfig
from understack_workflows.netapp.exceptions import ConfigurationError
from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.exceptions import NetworkOperationError
from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError
from understack_workflows.netapp.value_objects import AggregateResult
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
    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.HostConnection")
    def netapp_client(self, mock_host_connection, mock_config_module, mock_config):
        """Create a NetAppClient instance with mocked dependencies."""
        return NetAppClient(mock_config)

    def test_implements_interface(self, netapp_client):
        """Test that NetAppClient implements the NetAppClientInterface."""
        assert isinstance(netapp_client, NetAppClientInterface)

    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.HostConnection")
    def test_init_success(self, mock_host_connection, mock_config_module, mock_config):
        """Test successful NetAppClient initialization."""
        mock_config_module.CONNECTION = None

        NetAppClient(mock_config)

        mock_host_connection.assert_called_once_with(
            "test-netapp.example.com", username="test-user", password="test-password"
        )

    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.HostConnection")
    def test_init_connection_failure(
        self, mock_host_connection, mock_config_module, mock_config
    ):
        """Test NetApp client initialization with connection failure."""
        mock_config_module.CONNECTION = None
        mock_host_connection.side_effect = Exception("Connection failed")

        with pytest.raises(ConfigurationError) as exc_info:
            NetAppClient(mock_config)

        assert exc_info.value.config_path == "/test/config/path"
        assert exc_info.value.__cause__ is not None

    @patch("understack_workflows.netapp.client.Volume")
    @patch("understack_workflows.netapp.client.Svm")
    def test_create_svm_success(self, mock_svm_class, mock_volume_class, netapp_client):
        """Test successful SVM creation."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.name = "test-svm"
        mock_svm_instance.uuid = "svm-uuid-123"
        mock_svm_instance.state = "online"
        mock_svm_class.return_value = mock_svm_instance
        mock_root_volume = MagicMock()
        mock_volume_class.get_collection.return_value = [mock_root_volume]

        svm_spec = SvmSpec(name="test-svm", aggregate_name="test-aggregate")

        result = netapp_client.create_svm(svm_spec)

        assert isinstance(result, SvmResult)
        assert result.name == "test-svm"
        assert result.uuid == "svm-uuid-123"
        assert result.state == "online"
        mock_svm_instance.post.assert_called_once()
        mock_svm_instance.get.assert_called_once()
        mock_volume_class.get_collection.assert_called_once_with(
            name="test-svm_root",
            fields="uuid,name",
            **{"svm.name": "test-svm"},
        )
        assert mock_root_volume.size == 1024**3
        assert mock_root_volume.snapshot_policy == {"name": "none"}
        assert mock_root_volume.autosize == {
            "mode": "grow",
            "maximum": 2 * 1024**3,
        }
        mock_root_volume.patch.assert_called_once()

    @patch("understack_workflows.netapp.client.Svm")
    def test_create_svm_failure(self, mock_svm_class, netapp_client):
        """Test SVM creation failure."""
        mock_svm_instance = MagicMock()
        mock_svm_instance.post.side_effect = NetAppRestError("SVM creation failed")
        mock_svm_class.return_value = mock_svm_instance

        svm_spec = SvmSpec(name="test-svm", aggregate_name="test-aggregate")

        with pytest.raises(SvmOperationError) as exc_info:
            netapp_client.create_svm(svm_spec)

        assert exc_info.value.svm_name == "test-svm"
        assert exc_info.value.__cause__ is not None

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
        response = Mock()
        response.status_code = requests.codes.not_found
        response.json.return_value = {"error": {"message": "SVM not found"}}
        response.text = "SVM not found"
        mock_svm_class.find.side_effect = NetAppRestError(
            "SVM not found", cause=requests.HTTPError(response=response)
        )

        result = netapp_client.find_svm("missing-svm")

        assert result is None

    @patch("understack_workflows.netapp.client.Svm")
    def test_find_svm_netapp_error(self, mock_svm_class, netapp_client):
        """Test finding SVM when the API call fails."""
        mock_svm_class.find.side_effect = NetAppRestError("Connection error")

        with pytest.raises(SvmOperationError) as exc_info:
            netapp_client.find_svm("test-svm")

        assert exc_info.value.svm_name == "test-svm"
        assert exc_info.value.__cause__ is not None

    @patch("understack_workflows.netapp.client.Aggregate")
    def test_get_aggregates_success(self, mock_aggregate_class, netapp_client):
        """Test successful aggregate discovery."""
        mock_aggregate_a = MagicMock()
        mock_aggregate_a.name = "aggregate_a"
        mock_aggregate_a.state = "online"
        mock_aggregate_a.space.block_storage.used_percent = 30
        mock_aggregate_b = MagicMock()
        mock_aggregate_b.name = "aggregate_b"
        mock_aggregate_b.state = "online"
        mock_aggregate_b.space.block_storage.used_percent = 15
        mock_aggregate_class.get_collection.return_value = [
            mock_aggregate_a,
            mock_aggregate_b,
        ]

        result = netapp_client.get_aggregates()

        assert result == [
            AggregateResult(name="aggregate_a", state="online", used_percent=30),
            AggregateResult(name="aggregate_b", state="online", used_percent=15),
        ]

    @patch("understack_workflows.netapp.client.Aggregate")
    def test_get_aggregates_netapp_error(self, mock_aggregate_class, netapp_client):
        """Test aggregate discovery failure."""
        mock_aggregate_class.get_collection.side_effect = NetAppRestError(
            "Aggregate retrieval failed"
        )

        with pytest.raises(NetAppManagerError) as exc_info:
            netapp_client.get_aggregates()

        assert "Aggregate retrieval" in str(exc_info.value)
        assert exc_info.value.__cause__ is not None

    @patch("understack_workflows.netapp.client.Volume")
    def test_create_volume_success(self, mock_volume_class, netapp_client):
        """Test successful volume creation."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.name = "test-volume"
        mock_volume_instance.uuid = "volume-uuid-123"
        mock_volume_instance.size = 1024
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
        assert result.size == 1024
        assert result.state == "online"
        assert result.svm_name == "test-svm"

    @patch("understack_workflows.netapp.client.Volume")
    def test_create_volume_failure(self, mock_volume_class, netapp_client):
        """Test volume creation failure."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.post.side_effect = NetAppRestError(
            "Volume creation failed"
        )
        mock_volume_class.return_value = mock_volume_instance

        volume_spec = VolumeSpec(
            name="test-volume",
            svm_name="test-svm",
            aggregate_name="test-aggregate",
            size="1TB",
        )

        with pytest.raises(VolumeOperationError) as exc_info:
            netapp_client.create_volume(volume_spec)

        assert exc_info.value.volume_name == "test-volume"
        assert exc_info.value.__cause__ is not None

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
    def test_delete_volume_failure(self, mock_volume_class, netapp_client):
        """Test volume deletion failure."""
        mock_volume_instance = MagicMock()
        mock_volume_instance.get.side_effect = Exception("Volume not found")
        mock_volume_class.return_value = mock_volume_instance

        result = netapp_client.delete_volume("test-volume")

        assert result is False
        mock_volume_instance.get.assert_called_once_with(name="test-volume")
        mock_volume_instance.delete.assert_not_called()

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

        result = netapp_client.get_or_create_ip_interface(interface_spec)

        assert isinstance(result, InterfaceResult)
        assert result.name == "test-interface"
        assert result.uuid == "interface-uuid-123"
        assert str(result.address) == "192.168.1.10"
        assert result.netmask == "255.255.255.0"
        assert result.enabled is True
        assert result.svm_name == "test-svm"

    @patch("understack_workflows.netapp.client.IpInterface")
    def test_create_ip_interface_failure(self, mock_interface_class, netapp_client):
        """Test IP interface creation failure."""
        mock_interface_instance = MagicMock()
        mock_interface_instance.post.side_effect = NetAppRestError(
            "Interface creation failed"
        )
        mock_interface_class.return_value = mock_interface_instance

        interface_spec = InterfaceSpec(
            name="test-interface",
            address="192.168.1.10",
            netmask="255.255.255.0",
            svm_name="test-svm",
            home_port_uuid="port-uuid-123",
            broadcast_domain_name="test-domain",
        )

        with pytest.raises(NetworkOperationError) as exc_info:
            netapp_client.get_or_create_ip_interface(interface_spec)

        assert exc_info.value.interface_name == "test-interface"
        assert exc_info.value.__cause__ is not None

    @patch("understack_workflows.netapp.client.Port")
    def test_get_or_create_port_success(self, mock_port_class, netapp_client):
        """Test successful port creation."""
        mock_port_instance = MagicMock()
        mock_port_instance.uuid = "port-uuid-123"
        mock_port_instance.name = "e4a-100"
        mock_port_class.get_collection.return_value = iter([])
        mock_port_class.return_value = mock_port_instance

        port_spec = PortSpec(
            node_name="node-01",
            vlan_id=100,
            base_port_name="e4a",
            broadcast_domain_name="test-domain",
        )

        result = netapp_client.get_or_create_port(port_spec)

        assert isinstance(result, PortResult)
        assert result.uuid == "port-uuid-123"
        assert result.name == "e4a-100"
        assert result.node_name == "node-01"
        assert result.port_type == "vlan"

    @patch("understack_workflows.netapp.client.Port")
    def test_get_or_create_port_failure(self, mock_port_class, netapp_client):
        """Test port creation failure."""
        mock_port_instance = MagicMock()
        mock_port_instance.post.side_effect = NetAppRestError("Port creation failed")
        mock_port_class.get_collection.return_value = iter([])
        mock_port_class.return_value = mock_port_instance

        port_spec = PortSpec(
            node_name="node-01",
            vlan_id=100,
            base_port_name="e4a",
            broadcast_domain_name="test-domain",
        )

        with pytest.raises(NetworkOperationError) as exc_info:
            netapp_client.get_or_create_port(port_spec)

        assert exc_info.value.__cause__ is not None

    @patch("understack_workflows.netapp.client.Port")
    def test_get_broadcast_domain_name_success(self, mock_port_class, netapp_client):
        """Test successful broadcast domain lookup."""
        port = MagicMock()
        port.broadcast_domain.name = "Fabric-A"
        mock_port_class.get_collection.return_value = [port]

        result = netapp_client.get_broadcast_domain_name("node-01", "e4a")

        assert result == "Fabric-A"

    @patch("understack_workflows.netapp.client.Port")
    def test_get_broadcast_domain_name_not_found(self, mock_port_class, netapp_client):
        """Test broadcast domain lookup when no matching port exists."""
        mock_port_class.get_collection.return_value = []

        with pytest.raises(NetworkOperationError) as exc_info:
            netapp_client.get_broadcast_domain_name("node-01", "e4a")

        assert exc_info.value.context["node_name"] == "node-01"
        assert exc_info.value.context["port_name"] == "e4a"

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

        with pytest.raises(NetAppManagerError) as exc_info:
            netapp_client.get_nodes()

        assert "Node retrieval" in str(exc_info.value)

    @patch("understack_workflows.netapp.client.config")
    @patch("understack_workflows.netapp.client.NvmeNamespace")
    def test_get_namespaces_success(
        self, mock_namespace_class, mock_config_module, netapp_client
    ):
        """Test successful namespace retrieval."""
        mock_config_module.CONNECTION = MagicMock()
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

    @patch("understack_workflows.netapp.client.config")
    def test_get_namespaces_no_connection(self, mock_config_module, netapp_client):
        """Test namespace retrieval with no connection."""
        mock_config_module.CONNECTION = None

        namespace_spec = NamespaceSpec(svm_name="test-svm", volume_name="test-volume")

        result = netapp_client.get_namespaces(namespace_spec)

        assert result == []

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

        namespace_spec = NamespaceSpec(svm_name="test-svm", volume_name="test-volume")

        with pytest.raises(NetAppManagerError) as exc_info:
            netapp_client.get_namespaces(namespace_spec)

        assert "Namespace query" in str(exc_info.value)

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

        assert result.uuid == "route-uuid-123"
        assert result.gateway == "100.127.0.17"
        assert result.destination == "100.126.0.0/17"
        assert result.svm_name == "os-test-project"

    @patch("understack_workflows.netapp.client.NetworkRoute")
    def test_create_route_netapp_rest_error(self, mock_route_class, netapp_client):
        """Test route creation with NetAppRestError."""
        mock_route_instance = MagicMock()
        mock_route_instance.post.side_effect = NetAppRestError("SVM not found")
        mock_route_class.return_value = mock_route_instance

        route_spec = RouteSpec(
            svm_name="os-nonexistent-project",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
        )

        with pytest.raises(NetworkOperationError) as exc_info:
            netapp_client.create_route(route_spec)

        assert exc_info.value.context["svm_name"] == "os-nonexistent-project"
        assert exc_info.value.__cause__ is not None

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

        with pytest.raises(ValidationError):
            RouteSpec(
                svm_name="os-test-project",
                gateway="192.168.1.1",
                destination=ipaddress.IPv4Network("100.126.0.0/17"),
            )


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
            "get_or_create_ip_interface",
            "get_or_create_port",
            "get_broadcast_domain_name",
            "get_aggregates",
            "get_nodes",
            "get_namespaces",
            "create_route",
        }
        assert abstract_methods == expected_methods
