"""Tests for NetApp LIF Service."""

import ipaddress
from unittest.mock import Mock

import pytest

from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.lif_service import LifService
from understack_workflows.netapp.value_objects import InterfaceResult
from understack_workflows.netapp.value_objects import InterfaceSpec
from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig
from understack_workflows.netapp.value_objects import NodeResult
from understack_workflows.netapp.value_objects import PortResult
from understack_workflows.netapp.value_objects import PortSpec
from understack_workflows.netapp.value_objects import SvmResult


class TestLifService:
    """Test cases for LifService class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock NetApp client."""
        return Mock()

    @pytest.fixture
    def mock_error_handler(self):
        """Create a mock error handler."""
        return Mock()

    @pytest.fixture
    def lif_service(self, mock_client, mock_error_handler):
        """Create LifService instance with mocked dependencies."""
        return LifService(mock_client, mock_error_handler)

    @pytest.fixture
    def sample_config(self):
        """Create a sample NetappIPInterfaceConfig for testing."""
        return NetappIPInterfaceConfig(
            name="N1-lif-A",
            address=ipaddress.IPv4Address("192.168.1.10"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=100,
        )

    def test_create_lif_success(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test successful LIF creation."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        # Mock SVM exists
        mock_client.find_svm.return_value = SvmResult(
            name=expected_svm_name, uuid="svm-uuid-123", state="online"
        )

        # Mock port creation
        mock_port = PortResult(
            uuid="port-uuid-123", name="e4a-100", node_name="node-01", port_type="vlan"
        )
        mock_client.create_port.return_value = mock_port

        # Mock interface creation
        mock_interface = InterfaceResult(
            name=sample_config.name,
            uuid="interface-uuid-123",
            address=str(sample_config.address),
            netmask=str(sample_config.network.netmask),
            enabled=True,
            svm_name=expected_svm_name,
        )
        mock_client.create_ip_interface.return_value = mock_interface

        # Mock node identification
        mock_node = NodeResult(name="node-01", uuid="node-uuid-1")
        mock_client.get_nodes.return_value = [mock_node]

        lif_service.create_lif(project_id, sample_config)

        # Verify SVM was checked
        mock_client.find_svm.assert_called_once_with(expected_svm_name)

        # Verify port was created
        mock_client.create_port.assert_called_once()
        port_call_args = mock_client.create_port.call_args[0][0]
        assert isinstance(port_call_args, PortSpec)
        assert port_call_args.node_name == "node-01"
        assert port_call_args.vlan_id == 100

        # Verify interface was created
        mock_client.create_ip_interface.assert_called_once()
        interface_call_args = mock_client.create_ip_interface.call_args[0][0]
        assert isinstance(interface_call_args, InterfaceSpec)
        assert interface_call_args.name == sample_config.name
        assert interface_call_args.svm_name == expected_svm_name
        assert interface_call_args.home_port_uuid == mock_port.uuid

        # Verify logging
        mock_error_handler.log_info.assert_called()

    def test_create_lif_svm_not_found(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test LIF creation when SVM is not found."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        # Mock SVM doesn't exist
        mock_client.find_svm.return_value = None

        with pytest.raises(Exception, match="SVM Not Found"):
            lif_service.create_lif(project_id, sample_config)

        # Verify SVM was checked
        mock_client.find_svm.assert_called_once_with(expected_svm_name)

        # Verify no port or interface creation was attempted
        mock_client.create_port.assert_not_called()
        mock_client.create_ip_interface.assert_not_called()

    def test_create_lif_port_creation_error(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test LIF creation when port creation fails."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        # Mock SVM exists
        mock_client.find_svm.return_value = SvmResult(
            name=expected_svm_name, uuid="svm-uuid-123", state="online"
        )

        # Mock node identification
        mock_node = NodeResult(name="node-01", uuid="node-uuid-1")
        mock_client.get_nodes.return_value = [mock_node]

        # Mock port creation failure
        mock_client.create_port.side_effect = Exception("Port creation failed")
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "Operation failed"
        )

        with pytest.raises(NetAppManagerError):
            lif_service.create_lif(project_id, sample_config)

        # Verify error handler was called
        mock_error_handler.handle_operation_error.assert_called()

    def test_create_home_port_success(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test successful home port creation."""
        # Mock node identification
        mock_node = NodeResult(name="node-01", uuid="node-uuid-1")
        mock_client.get_nodes.return_value = [mock_node]

        # Mock port creation
        mock_port = PortResult(
            uuid="port-uuid-123", name="e4a-100", node_name="node-01", port_type="vlan"
        )
        mock_client.create_port.return_value = mock_port

        result = lif_service.create_home_port(sample_config)

        assert result == mock_port

        # Verify port was created with correct specification
        mock_client.create_port.assert_called_once()
        call_args = mock_client.create_port.call_args[0][0]
        assert isinstance(call_args, PortSpec)
        assert call_args.node_name == "node-01"
        assert call_args.vlan_id == 100
        assert call_args.base_port_name == sample_config.base_port_name
        assert call_args.broadcast_domain_name == sample_config.broadcast_domain_name

    def test_create_home_port_no_node(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test home port creation when no suitable node is found."""
        # Mock no matching nodes
        mock_client.get_nodes.return_value = [
            NodeResult(name="node-03", uuid="node-uuid-3"),
            NodeResult(name="node-04", uuid="node-uuid-4"),
        ]

        with pytest.raises(Exception, match="Could not find home node"):
            lif_service.create_home_port(sample_config)

        # Verify no port creation was attempted
        mock_client.create_port.assert_not_called()

    def test_identify_home_node_success(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test successful node identification."""
        # Mock nodes with different numbers
        mock_nodes = [
            NodeResult(name="node-01", uuid="node-uuid-1"),
            NodeResult(name="node-02", uuid="node-uuid-2"),
            NodeResult(name="node-03", uuid="node-uuid-3"),
        ]
        mock_client.get_nodes.return_value = mock_nodes

        # sample_config has name "N1-lif-A" which should match node-01
        result = lif_service.identify_home_node(sample_config)

        assert result == mock_nodes[0]  # node-01
        mock_client.get_nodes.assert_called_once()

    def test_identify_home_node_n2_interface(
        self, lif_service, mock_client, mock_error_handler
    ):
        """Test node identification for N2 interface."""
        config = NetappIPInterfaceConfig(
            name="N2-lif-B",
            address=ipaddress.IPv4Address("192.168.1.11"),
            network=ipaddress.IPv4Network("192.168.1.0/24"),
            vlan_id=200,
        )

        # Mock nodes
        mock_nodes = [
            NodeResult(name="node-01", uuid="node-uuid-1"),
            NodeResult(name="node-02", uuid="node-uuid-2"),
        ]
        mock_client.get_nodes.return_value = mock_nodes

        # N2 interface should match node-02
        result = lif_service.identify_home_node(config)

        assert result == mock_nodes[1]  # node-02

    def test_identify_home_node_not_found(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test node identification when no matching node is found."""
        # Mock nodes that don't match the desired node number
        mock_nodes = [
            NodeResult(name="node-03", uuid="node-uuid-3"),
            NodeResult(name="node-04", uuid="node-uuid-4"),
        ]
        mock_client.get_nodes.return_value = mock_nodes

        result = lif_service.identify_home_node(sample_config)

        assert result is None
        mock_error_handler.log_warning.assert_called()

    def test_identify_home_node_exception(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test node identification when client raises an exception."""
        mock_client.get_nodes.side_effect = Exception("NetApp error")

        result = lif_service.identify_home_node(sample_config)

        assert result is None
        mock_error_handler.log_warning.assert_called()

    def test_svm_name_generation(self, lif_service):
        """Test SVM name generation follows naming convention."""
        project_id = "test-project-456"
        expected_svm_name = "os-test-project-456"

        result = lif_service._get_svm_name(project_id)

        assert result == expected_svm_name

    def test_interface_spec_creation(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test that interface specification is created correctly."""
        project_id = "test-project-789"
        expected_svm_name = "os-test-project-789"

        # Mock SVM exists
        mock_client.find_svm.return_value = SvmResult(
            name=expected_svm_name, uuid="svm-uuid-123", state="online"
        )

        # Mock port creation
        mock_port = PortResult(
            uuid="port-uuid-123", name="e4a-100", node_name="node-01", port_type="vlan"
        )
        mock_client.create_port.return_value = mock_port

        # Mock interface creation
        mock_client.create_ip_interface.return_value = InterfaceResult(
            name=sample_config.name,
            uuid="interface-uuid-123",
            address=str(sample_config.address),
            netmask=str(sample_config.network.netmask),
            enabled=True,
        )

        # Mock node identification
        mock_node = NodeResult(name="node-01", uuid="node-uuid-1")
        mock_client.get_nodes.return_value = [mock_node]

        lif_service.create_lif(project_id, sample_config)

        # Verify the interface spec is created correctly
        interface_call_args = mock_client.create_ip_interface.call_args[0][0]
        assert interface_call_args.name == sample_config.name
        assert str(interface_call_args.address) == str(sample_config.address)
        assert interface_call_args.netmask == str(sample_config.network.netmask)
        assert interface_call_args.svm_name == expected_svm_name
        assert interface_call_args.home_port_uuid == mock_port.uuid
        assert (
            interface_call_args.broadcast_domain_name
            == sample_config.broadcast_domain_name
        )
        assert interface_call_args.service_policy == "default-data-nvme-tcp"

    def test_port_spec_creation(
        self, lif_service, mock_client, mock_error_handler, sample_config
    ):
        """Test that port specification is created correctly."""
        # Mock node identification
        mock_node = NodeResult(name="node-01", uuid="node-uuid-1")
        mock_client.get_nodes.return_value = [mock_node]

        # Mock port creation
        mock_client.create_port.return_value = PortResult(
            uuid="port-uuid-123", name="e4a-100", node_name="node-01", port_type="vlan"
        )

        lif_service.create_home_port(sample_config)

        # Verify the port spec is created correctly
        port_call_args = mock_client.create_port.call_args[0][0]
        assert port_call_args.node_name == "node-01"
        assert port_call_args.vlan_id == sample_config.vlan_id
        assert port_call_args.base_port_name == sample_config.base_port_name
        assert (
            port_call_args.broadcast_domain_name == sample_config.broadcast_domain_name
        )

    def test_node_number_extraction_logic(
        self, lif_service, mock_client, mock_error_handler
    ):
        """Test the node number extraction logic with various node names."""
        test_cases = [
            ("node-01", "N1-lif-A", 1),
            ("node-02", "N2-lif-B", 2),
            ("cluster-node-01", "N1-lif-A", 1),
            ("netapp-node-02", "N2-lif-B", 2),
        ]

        for node_name, interface_name, expected_number in test_cases:
            config = NetappIPInterfaceConfig(
                name=interface_name,
                address=ipaddress.IPv4Address("192.168.1.10"),
                network=ipaddress.IPv4Network("192.168.1.0/24"),
                vlan_id=100,
            )

            mock_nodes = [NodeResult(name=node_name, uuid=f"uuid-{expected_number}")]
            mock_client.get_nodes.return_value = mock_nodes

            result = lif_service.identify_home_node(config)

            assert result is not None
            assert result.name == node_name
