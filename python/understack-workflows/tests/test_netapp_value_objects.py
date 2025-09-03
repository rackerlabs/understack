"""Tests for NetApp value objects."""

import ipaddress

import pytest

from understack_workflows.netapp.value_objects import InterfaceResult
from understack_workflows.netapp.value_objects import InterfaceSpec
from understack_workflows.netapp.value_objects import NamespaceResult
from understack_workflows.netapp.value_objects import NamespaceSpec
from understack_workflows.netapp.value_objects import NodeResult
from understack_workflows.netapp.value_objects import PortResult
from understack_workflows.netapp.value_objects import PortSpec
from understack_workflows.netapp.value_objects import RouteResult
from understack_workflows.netapp.value_objects import RouteSpec
from understack_workflows.netapp.value_objects import SvmResult
from understack_workflows.netapp.value_objects import SvmSpec
from understack_workflows.netapp.value_objects import VolumeResult
from understack_workflows.netapp.value_objects import VolumeSpec


class TestSvmSpec:
    """Test cases for SvmSpec value object."""

    def test_valid_svm_spec(self):
        """Test creating a valid SVM specification."""
        spec = SvmSpec(
            name="test-svm",
            aggregate_name="aggr1",
            language="c.utf_8",
            allowed_protocols=["nvme"],
        )

        assert spec.name == "test-svm"
        assert spec.aggregate_name == "aggr1"
        assert spec.language == "c.utf_8"
        assert spec.allowed_protocols == ["nvme"]
        assert spec.root_volume_name == "test-svm_root"

    def test_svm_spec_defaults(self):
        """Test SVM specification with default values."""
        spec = SvmSpec(name="test-svm", aggregate_name="aggr1")

        assert spec.language == "c.utf_8"
        assert spec.allowed_protocols == ["nvme"]

    def test_svm_spec_multiple_protocols(self):
        """Test SVM specification with multiple protocols."""
        spec = SvmSpec(
            name="test-svm",
            aggregate_name="aggr1",
            allowed_protocols=["nvme", "nfs", "iscsi"],
        )

        assert spec.allowed_protocols == ["nvme", "nfs", "iscsi"]

    def test_svm_spec_immutable(self):
        """Test that SVM specification is immutable."""
        spec = SvmSpec(name="test-svm", aggregate_name="aggr1")

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            spec.name = "new-name"  # type: ignore[misc]


class TestVolumeSpec:
    """Test cases for VolumeSpec value object."""

    def test_valid_volume_spec(self):
        """Test creating a valid volume specification."""
        spec = VolumeSpec(
            name="test-volume", svm_name="test-svm", aggregate_name="aggr1", size="1TB"
        )

        assert spec.name == "test-volume"
        assert spec.svm_name == "test-svm"
        assert spec.aggregate_name == "aggr1"
        assert spec.size == "1TB"

    def test_volume_spec_various_sizes(self):
        """Test volume specification with various size formats."""
        sizes = ["1TB", "500GB", "1.5TB", "100MB", "1KB", "1024B", "invalid-size"]

        for size in sizes:
            spec = VolumeSpec(
                name="test-volume",
                svm_name="test-svm",
                aggregate_name="aggr1",
                size=size,
            )
            assert spec.size == size

    def test_volume_spec_immutable(self):
        """Test that volume specification is immutable."""
        spec = VolumeSpec(
            name="test-volume", svm_name="test-svm", aggregate_name="aggr1", size="1TB"
        )

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            spec.name = "new-name"  # type: ignore[misc]


class TestInterfaceSpec:
    """Test cases for InterfaceSpec value object."""

    def test_valid_interface_spec(self):
        """Test creating a valid interface specification."""
        spec = InterfaceSpec(
            name="test-lif",
            address="192.168.1.10",
            netmask="255.255.255.0",
            svm_name="test-svm",
            home_port_uuid="port-uuid-123",
            broadcast_domain_name="Fabric-A",
        )

        assert spec.name == "test-lif"
        assert str(spec.address) == "192.168.1.10"
        assert spec.netmask == "255.255.255.0"
        assert spec.svm_name == "test-svm"
        assert spec.home_port_uuid == "port-uuid-123"
        assert spec.broadcast_domain_name == "Fabric-A"
        assert spec.service_policy == "default-data-nvme-tcp"

    def test_interface_spec_custom_service_policy(self):
        """Test interface specification with custom service policy."""
        spec = InterfaceSpec(
            name="test-lif",
            address="192.168.1.10",
            netmask="255.255.255.0",
            svm_name="test-svm",
            home_port_uuid="port-uuid-123",
            broadcast_domain_name="Fabric-A",
            service_policy="custom-policy",
        )

        assert spec.service_policy == "custom-policy"

    def test_interface_spec_ip_info_property(self):
        """Test interface specification IP info property."""
        spec = InterfaceSpec(
            name="test-lif",
            address="192.168.1.10",
            netmask="255.255.255.0",
            svm_name="test-svm",
            home_port_uuid="port-uuid-123",
            broadcast_domain_name="Fabric-A",
        )

        expected_ip_info = {"address": "192.168.1.10", "netmask": "255.255.255.0"}
        assert spec.ip_info == expected_ip_info

    def test_interface_spec_invalid_ip_address(self):
        """Test interface specification with invalid IP address."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            InterfaceSpec(
                name="test-lif",
                address="invalid-ip",
                netmask="255.255.255.0",
                svm_name="test-svm",
                home_port_uuid="port-uuid-123",
                broadcast_domain_name="Fabric-A",
            )

    def test_interface_spec_immutable(self):
        """Test that interface specification is immutable."""
        spec = InterfaceSpec(
            name="test-lif",
            address="192.168.1.10",
            netmask="255.255.255.0",
            svm_name="test-svm",
            home_port_uuid="port-uuid-123",
            broadcast_domain_name="Fabric-A",
        )

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            spec.name = "new-name"  # type: ignore[misc]


class TestPortSpec:
    """Test cases for PortSpec value object."""

    def test_valid_port_spec(self):
        """Test creating a valid port specification."""
        spec = PortSpec(
            node_name="node-01",
            vlan_id=100,
            base_port_name="e4a",
            broadcast_domain_name="Fabric-A",
        )

        assert spec.node_name == "node-01"
        assert spec.vlan_id == 100
        assert spec.base_port_name == "e4a"
        assert spec.broadcast_domain_name == "Fabric-A"

    def test_port_spec_vlan_config_property(self):
        """Test port specification VLAN config property."""
        spec = PortSpec(
            node_name="node-01",
            vlan_id=100,
            base_port_name="e4a",
            broadcast_domain_name="Fabric-A",
        )

        expected_vlan_config = {
            "tag": 100,
            "base_port": {"name": "e4a", "node": {"name": "node-01"}},
        }
        assert spec.vlan_config == expected_vlan_config

    def test_port_spec_various_vlan_ids(self):
        """Test port specification with various valid VLAN IDs."""
        valid_vlan_ids = [1, 100, 4094]  # Valid VLAN IDs

        for vlan_id in valid_vlan_ids:
            spec = PortSpec(
                node_name="node-01",
                vlan_id=vlan_id,
                base_port_name="e4a",
                broadcast_domain_name="Fabric-A",
            )
            assert spec.vlan_id == vlan_id

    def test_port_spec_invalid_vlan_ids(self):
        """Test port specification with invalid VLAN IDs."""
        from pydantic import ValidationError

        invalid_vlan_ids = [0, 4095, 5000, -1]  # Invalid VLAN IDs

        for vlan_id in invalid_vlan_ids:
            with pytest.raises(ValidationError):
                PortSpec(
                    node_name="node-01",
                    vlan_id=vlan_id,
                    base_port_name="e4a",
                    broadcast_domain_name="Fabric-A",
                )

    def test_port_spec_immutable(self):
        """Test that port specification is immutable."""
        spec = PortSpec(
            node_name="node-01",
            vlan_id=100,
            base_port_name="e4a",
            broadcast_domain_name="Fabric-A",
        )

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            spec.vlan_id = 200  # type: ignore[misc]


class TestNamespaceSpec:
    """Test cases for NamespaceSpec value object."""

    def test_valid_namespace_spec(self):
        """Test creating a valid namespace specification."""
        spec = NamespaceSpec(svm_name="test-svm", volume_name="test-volume")

        assert spec.svm_name == "test-svm"
        assert spec.volume_name == "test-volume"

    def test_namespace_spec_query_string(self):
        """Test namespace specification query string property."""
        spec = NamespaceSpec(svm_name="test-svm", volume_name="test-volume")

        expected_query = "svm.name=test-svm&location.volume.name=test-volume"
        assert spec.query_string == expected_query

    def test_namespace_spec_immutable(self):
        """Test that namespace specification is immutable."""
        spec = NamespaceSpec(svm_name="test-svm", volume_name="test-volume")

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            spec.svm_name = "new-svm"  # type: ignore[misc]


class TestSvmResult:
    """Test cases for SvmResult value object."""

    def test_valid_svm_result(self):
        """Test creating a valid SVM result."""
        result = SvmResult(name="test-svm", uuid="svm-uuid-123", state="online")

        assert result.name == "test-svm"
        assert result.uuid == "svm-uuid-123"
        assert result.state == "online"

    def test_svm_result_various_states(self):
        """Test SVM result with various states."""
        states = [
            "online",
            "offline",
            "starting",
            "stopping",
            "stopped",
            "unknown",
            "new-state",
        ]

        for state in states:
            result = SvmResult(name="test-svm", uuid="svm-uuid-123", state=state)
            assert result.state == state

    def test_svm_result_pydantic_serialization(self):
        """Test Pydantic serialization and deserialization of SvmResult."""
        result = SvmResult(name="test-svm", uuid="svm-uuid-123", state="online")

        # Test JSON serialization
        json_data = result.model_dump_json()
        assert '"name":"test-svm"' in json_data
        assert '"uuid":"svm-uuid-123"' in json_data
        assert '"state":"online"' in json_data

        # Test dictionary serialization
        dict_data = result.model_dump()
        expected_dict = {
            "name": "test-svm",
            "uuid": "svm-uuid-123",
            "state": "online"
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = SvmResult.model_validate(dict_data)
        assert recreated_result == result


class TestVolumeResult:
    """Test cases for VolumeResult value object."""

    def test_valid_volume_result(self):
        """Test creating a valid volume result."""
        result = VolumeResult(
            name="test-volume",
            uuid="vol-uuid-123",
            size="1TB",
            state="online",
            svm_name="test-svm",
        )

        assert result.name == "test-volume"
        assert result.uuid == "vol-uuid-123"
        assert result.size == "1TB"
        assert result.state == "online"
        assert result.svm_name == "test-svm"

    def test_volume_result_without_svm_name(self):
        """Test volume result without SVM name."""
        result = VolumeResult(
            name="test-volume", uuid="vol-uuid-123", size="1TB", state="online"
        )

        assert result.svm_name is None

    def test_volume_result_various_states(self):
        """Test volume result with various states."""
        states = ["online", "offline", "restricted", "mixed", "unknown", "new-state"]

        for state in states:
            result = VolumeResult(
                name="test-volume", uuid="vol-uuid-123", size="1TB", state=state
            )
            assert result.state == state

    def test_volume_result_pydantic_serialization(self):
        """Test Pydantic serialization and deserialization of VolumeResult."""
        result = VolumeResult(
            name="test-volume",
            uuid="vol-uuid-123",
            size="1TB",
            state="online",
            svm_name="test-svm"
        )

        # Test JSON serialization
        json_data = result.model_dump_json()
        assert '"name":"test-volume"' in json_data
        assert '"uuid":"vol-uuid-123"' in json_data
        assert '"size":"1TB"' in json_data
        assert '"state":"online"' in json_data
        assert '"svm_name":"test-svm"' in json_data

        # Test dictionary serialization
        dict_data = result.model_dump()
        expected_dict = {
            "name": "test-volume",
            "uuid": "vol-uuid-123",
            "size": "1TB",
            "state": "online",
            "svm_name": "test-svm"
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = VolumeResult.model_validate(dict_data)
        assert recreated_result == result

    def test_volume_result_pydantic_serialization_without_svm_name(self):
        """Test Pydantic serialization with None svm_name."""
        result = VolumeResult(
            name="test-volume",
            uuid="vol-uuid-123",
            size="1TB",
            state="online"
        )

        # Test dictionary serialization with None value
        dict_data = result.model_dump()
        expected_dict = {
            "name": "test-volume",
            "uuid": "vol-uuid-123",
            "size": "1TB",
            "state": "online",
            "svm_name": None
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = VolumeResult.model_validate(dict_data)
        assert recreated_result == result
        assert recreated_result.svm_name is None


class TestNodeResult:
    """Test cases for NodeResult value object."""

    def test_valid_node_result(self):
        """Test creating a valid node result."""
        result = NodeResult(name="node-01", uuid="node-uuid-123")

        assert result.name == "node-01"
        assert result.uuid == "node-uuid-123"

    def test_node_result_pydantic_serialization(self):
        """Test Pydantic serialization and deserialization of NodeResult."""
        result = NodeResult(name="node-01", uuid="node-uuid-123")

        # Test JSON serialization
        json_data = result.model_dump_json()
        assert '"name":"node-01"' in json_data
        assert '"uuid":"node-uuid-123"' in json_data

        # Test dictionary serialization
        dict_data = result.model_dump()
        expected_dict = {
            "name": "node-01",
            "uuid": "node-uuid-123"
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = NodeResult.model_validate(dict_data)
        assert recreated_result == result


class TestPortResult:
    """Test cases for PortResult value object."""

    def test_valid_port_result(self):
        """Test creating a valid port result."""
        result = PortResult(
            uuid="port-uuid-123", name="e4a-100", node_name="node-01", port_type="vlan"
        )

        assert result.uuid == "port-uuid-123"
        assert result.name == "e4a-100"
        assert result.node_name == "node-01"
        assert result.port_type == "vlan"

    def test_port_result_without_type(self):
        """Test port result without port type."""
        result = PortResult(uuid="port-uuid-123", name="e4a-100", node_name="node-01")

        assert result.port_type is None

    def test_port_result_pydantic_serialization(self):
        """Test Pydantic serialization and deserialization of PortResult."""
        result = PortResult(
            uuid="port-uuid-123",
            name="e4a-100",
            node_name="node-01",
            port_type="vlan"
        )

        # Test JSON serialization
        json_data = result.model_dump_json()
        assert '"uuid":"port-uuid-123"' in json_data
        assert '"name":"e4a-100"' in json_data
        assert '"node_name":"node-01"' in json_data
        assert '"port_type":"vlan"' in json_data

        # Test dictionary serialization
        dict_data = result.model_dump()
        expected_dict = {
            "uuid": "port-uuid-123",
            "name": "e4a-100",
            "node_name": "node-01",
            "port_type": "vlan"
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = PortResult.model_validate(dict_data)
        assert recreated_result == result

    def test_port_result_pydantic_serialization_without_type(self):
        """Test Pydantic serialization with None port_type."""
        result = PortResult(
            uuid="port-uuid-123",
            name="e4a-100",
            node_name="node-01"
        )

        # Test dictionary serialization with None value
        dict_data = result.model_dump()
        expected_dict = {
            "uuid": "port-uuid-123",
            "name": "e4a-100",
            "node_name": "node-01",
            "port_type": None
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = PortResult.model_validate(dict_data)
        assert recreated_result == result
        assert recreated_result.port_type is None


class TestInterfaceResult:
    """Test cases for InterfaceResult value object."""

    def test_valid_interface_result(self):
        """Test creating a valid interface result."""
        result = InterfaceResult(
            name="test-lif",
            uuid="lif-uuid-123",
            address="192.168.1.10",
            netmask="255.255.255.0",
            enabled=True,
            svm_name="test-svm",
        )

        assert result.name == "test-lif"
        assert result.uuid == "lif-uuid-123"
        assert str(result.address) == "192.168.1.10"
        assert result.netmask == "255.255.255.0"
        assert result.enabled is True
        assert result.svm_name == "test-svm"

    def test_interface_result_without_svm_name(self):
        """Test interface result without SVM name."""
        result = InterfaceResult(
            name="test-lif",
            uuid="lif-uuid-123",
            address="192.168.1.10",
            netmask="255.255.255.0",
            enabled=True,
        )

        assert result.svm_name is None

    def test_interface_result_disabled(self):
        """Test interface result when disabled."""
        result = InterfaceResult(
            name="test-lif",
            uuid="lif-uuid-123",
            address="192.168.1.10",
            netmask="255.255.255.0",
            enabled=False,
        )

        assert result.enabled is False

    def test_interface_result_pydantic_serialization(self):
        """Test Pydantic serialization and deserialization of InterfaceResult."""
        result = InterfaceResult(
            name="test-lif",
            uuid="lif-uuid-123",
            address="192.168.1.10",
            netmask="255.255.255.0",
            enabled=True,
            svm_name="test-svm"
        )

        # Test JSON serialization
        json_data = result.model_dump_json()
        assert '"name":"test-lif"' in json_data
        assert '"uuid":"lif-uuid-123"' in json_data
        assert '"address":"192.168.1.10"' in json_data
        assert '"netmask":"255.255.255.0"' in json_data
        assert '"enabled":true' in json_data
        assert '"svm_name":"test-svm"' in json_data

        # Test dictionary serialization (mode='json' converts IPv4Address to string)
        dict_data = result.model_dump(mode='json')
        expected_dict = {
            "name": "test-lif",
            "uuid": "lif-uuid-123",
            "address": "192.168.1.10",
            "netmask": "255.255.255.0",
            "enabled": True,
            "svm_name": "test-svm"
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = InterfaceResult.model_validate(dict_data)
        assert recreated_result == result

    def test_interface_result_ip_validation(self):
        """Test IPv4Address validation for InterfaceResult address field."""
        # Test valid IP address
        result = InterfaceResult(
            name="test-lif",
            uuid="lif-uuid-123",
            address="10.0.0.1",
            netmask="255.255.255.0",
            enabled=True
        )
        assert str(result.address) == "10.0.0.1"

        # Test that string addresses are accepted (backward compatibility)
        result_str = InterfaceResult(
            name="test-lif",
            uuid="lif-uuid-123",
            address="invalid-ip",  # This is now allowed as a string
            netmask="255.255.255.0",
            enabled=True
        )
        assert result_str.address == "invalid-ip"


class TestNamespaceResult:
    """Test cases for NamespaceResult value object."""

    def test_valid_namespace_result(self):
        """Test creating a valid namespace result."""
        result = NamespaceResult(
            uuid="ns-uuid-123",
            name="namespace-1",
            mapped=True,
            svm_name="test-svm",
            volume_name="test-volume",
        )

        assert result.uuid == "ns-uuid-123"
        assert result.name == "namespace-1"
        assert result.mapped is True
        assert result.svm_name == "test-svm"
        assert result.volume_name == "test-volume"

    def test_namespace_result_not_mapped(self):
        """Test namespace result when not mapped."""
        result = NamespaceResult(uuid="ns-uuid-123", name="namespace-1", mapped=False)

        assert result.mapped is False

    def test_namespace_result_without_optional_fields(self):
        """Test namespace result without optional fields."""
        result = NamespaceResult(uuid="ns-uuid-123", name="namespace-1", mapped=False)

        assert result.svm_name is None
        assert result.volume_name is None

    def test_namespace_result_pydantic_serialization(self):
        """Test Pydantic serialization and deserialization of NamespaceResult."""
        result = NamespaceResult(
            uuid="ns-uuid-123",
            name="namespace-1",
            mapped=True,
            svm_name="test-svm",
            volume_name="test-volume"
        )

        # Test JSON serialization
        json_data = result.model_dump_json()
        assert '"uuid":"ns-uuid-123"' in json_data
        assert '"name":"namespace-1"' in json_data
        assert '"mapped":true' in json_data
        assert '"svm_name":"test-svm"' in json_data
        assert '"volume_name":"test-volume"' in json_data

        # Test dictionary serialization
        dict_data = result.model_dump()
        expected_dict = {
            "uuid": "ns-uuid-123",
            "name": "namespace-1",
            "mapped": True,
            "svm_name": "test-svm",
            "volume_name": "test-volume"
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = NamespaceResult.model_validate(dict_data)
        assert recreated_result == result

    def test_namespace_result_pydantic_serialization_without_optional_fields(self):
        """Test Pydantic serialization with None optional fields."""
        result = NamespaceResult(
            uuid="ns-uuid-123",
            name="namespace-1",
            mapped=False
        )

        # Test dictionary serialization with None values
        dict_data = result.model_dump()
        expected_dict = {
            "uuid": "ns-uuid-123",
            "name": "namespace-1",
            "mapped": False,
            "svm_name": None,
            "volume_name": None
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = NamespaceResult.model_validate(dict_data)
        assert recreated_result == result
        assert recreated_result.svm_name is None
        assert recreated_result.volume_name is None


class TestRouteSpec:
    """Test cases for RouteSpec value object."""

    def test_valid_route_spec(self):
        """Test creating a valid route specification."""
        spec = RouteSpec(
            svm_name="os-test-project",
            gateway="100.127.0.17",
            destination="100.126.0.0/17",
        )

        assert spec.svm_name == "os-test-project"
        assert str(spec.gateway) == "100.127.0.17"
        assert str(spec.destination) == "100.126.0.0/17"

    def test_route_spec_immutable(self):
        """Test that route specification is immutable."""
        spec = RouteSpec(
            svm_name="os-test-project",
            gateway="100.127.0.17",
            destination="100.126.0.0/17",
        )

        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            spec.svm_name = "new-svm"  # type: ignore[misc]

    def test_from_nexthop_ip_third_octet_zero(self):
        """Test route destination calculation for third octet = 0."""
        spec = RouteSpec.from_nexthop_ip("os-test-project", "100.127.0.17")

        assert spec.svm_name == "os-test-project"
        assert str(spec.gateway) == "100.127.0.17"
        assert str(spec.destination) == "100.126.0.0/17"

    def test_from_nexthop_ip_third_octet_128(self):
        """Test route destination calculation for third octet = 128."""
        spec = RouteSpec.from_nexthop_ip("os-test-project", "100.127.128.17")

        assert spec.svm_name == "os-test-project"
        assert str(spec.gateway) == "100.127.128.17"
        assert str(spec.destination) == "100.126.128.0/17"

    def test_from_nexthop_ip_various_valid_ips(self):
        """Test route destination calculation with various valid IP patterns."""
        test_cases = [
            ("100.64.0.1", ipaddress.IPv4Network("100.126.0.0/17")),
            ("100.65.0.254", ipaddress.IPv4Network("100.126.0.0/17")),
            ("100.66.128.1", ipaddress.IPv4Network("100.126.128.0/17")),
            ("100.67.128.100", ipaddress.IPv4Network("100.126.128.0/17")),
        ]

        for nexthop_ip, expected_destination in test_cases:
            spec = RouteSpec.from_nexthop_ip("os-test-project", nexthop_ip)
            assert spec.destination == expected_destination
            assert str(spec.gateway) == nexthop_ip

    def test_calculate_destination_third_octet_zero(self):
        """Test _calculate_destination static method for third octet = 0."""
        destination = RouteSpec._calculate_destination("100.127.0.17")
        assert destination == ipaddress.IPv4Network("100.126.0.0/17")

    def test_calculate_destination_third_octet_128(self):
        """Test _calculate_destination static method for third octet = 128."""
        destination = RouteSpec._calculate_destination("100.127.128.17")
        assert destination == ipaddress.IPv4Network("100.126.128.0/17")

    def test_calculate_destination_invalid_pattern(self):
        """Test _calculate_destination with unsupported third octet values."""
        invalid_ips = [
            "100.127.1.17",
            "100.127.64.17",
            "100.127.127.17",
            "100.127.129.17",
            "100.127.255.17",
        ]

        for invalid_ip in invalid_ips:
            with pytest.raises(ValueError, match="Unsupported IP pattern"):
                RouteSpec._calculate_destination(invalid_ip)

    def test_from_nexthop_ip_invalid_pattern(self):
        """Test from_nexthop_ip with unsupported IP patterns."""
        with pytest.raises(ValueError, match="Unsupported IP pattern"):
            RouteSpec.from_nexthop_ip("os-test-project", "100.127.64.17")

    def test_calculate_destination_invalid_ip_format(self):
        """Test _calculate_destination with invalid IP format."""
        invalid_formats = [
            "not.an.ip.address",
            "256.256.256.256",
            "192.168.1",
            "192.168.1.1.1",
            "",
        ]

        for invalid_format in invalid_formats:
            with pytest.raises((ValueError, ipaddress.AddressValueError)):
                RouteSpec._calculate_destination(invalid_format)

    def test_calculate_destination_comprehensive_third_octet_zero(self):
        """Test comprehensive route destination calculation for third octet = 0."""
        # Test various IP addresses with third octet = 0 within 100.64.0.0/10 subnet
        test_ips = [
            "100.64.0.1",
            "100.65.0.1",
            "100.66.0.254",
            "100.67.0.100",
            "100.68.0.3",
            "100.127.0.255",
        ]

        for ip in test_ips:
            destination = RouteSpec._calculate_destination(ip)
            assert destination == ipaddress.IPv4Network(
                "100.126.0.0/17"
            ), f"Failed for IP: {ip}"

    def test_calculate_destination_comprehensive_third_octet_128(self):
        """Test comprehensive route destination calculation for third octet = 128."""
        # Test various IP addresses with third octet = 128 within 100.64.0.0/10 subnet
        test_ips = [
            "100.64.128.1",
            "100.65.128.1",
            "100.66.128.254",
            "100.67.128.100",
            "100.68.128.3",
            "100.127.128.255",
        ]

        for ip in test_ips:
            destination = RouteSpec._calculate_destination(ip)
            assert destination == ipaddress.IPv4Network(
                "100.126.128.0/17"
            ), f"Failed for IP: {ip}"

    def test_calculate_destination_comprehensive_invalid_patterns(self):
        """Test comprehensive error handling for all invalid third octet values."""
        # Test all invalid third octet values (not 0 or 128) within 100.64.0.0/10 subnet
        invalid_third_octets = [1, 2, 63, 64, 127, 129, 192, 254, 255]

        for third_octet in invalid_third_octets:
            invalid_ip = f"100.64.{third_octet}.1"
            with pytest.raises(ValueError, match="Unsupported IP pattern"):
                RouteSpec._calculate_destination(invalid_ip)

    def test_from_nexthop_ip_comprehensive_valid_patterns(self):
        """Test RouteSpec.from_nexthop_ip with comprehensive valid IP patterns."""
        # Test cases: (nexthop_ip, expected_destination) - all within 100.64.0.0/10
        test_cases = [
            # Third octet = 0 cases
            ("100.64.0.1", ipaddress.IPv4Network("100.126.0.0/17")),
            ("100.65.0.254", ipaddress.IPv4Network("100.126.0.0/17")),
            ("100.66.0.100", ipaddress.IPv4Network("100.126.0.0/17")),
            ("100.67.0.50", ipaddress.IPv4Network("100.126.0.0/17")),
            (
                "100.127.0.17",
                ipaddress.IPv4Network("100.126.0.0/17"),
            ),  # From design document example
            # Third octet = 128 cases
            ("100.64.128.1", ipaddress.IPv4Network("100.126.128.0/17")),
            ("100.65.128.254", ipaddress.IPv4Network("100.126.128.0/17")),
            ("100.66.128.100", ipaddress.IPv4Network("100.126.128.0/17")),
            ("100.67.128.50", ipaddress.IPv4Network("100.126.128.0/17")),
            (
                "100.127.128.17",
                ipaddress.IPv4Network("100.126.128.0/17"),
            ),  # From design document example
        ]

        svm_name = "os-550e8400-e29b-41d4-a716-446655440000"  # Valid UUID format

        for nexthop_ip, expected_destination in test_cases:
            spec = RouteSpec.from_nexthop_ip(svm_name, nexthop_ip)
            assert spec.svm_name == svm_name
            assert str(spec.gateway) == nexthop_ip
            assert spec.destination == expected_destination

    def test_from_nexthop_ip_comprehensive_invalid_patterns(self):
        """Test RouteSpec.from_nexthop_ip with comprehensive invalid IP patterns."""
        svm_name = "os-550e8400-e29b-41d4-a716-446655440000"

        # Test invalid third octet values within 100.64.0.0/10 subnet
        invalid_third_octets = [1, 2, 63, 64, 127, 129, 192, 254, 255]

        for third_octet in invalid_third_octets:
            invalid_ip = f"100.64.{third_octet}.1"
            with pytest.raises(ValueError, match="Unsupported IP pattern"):
                RouteSpec.from_nexthop_ip(svm_name, invalid_ip)

    def test_from_nexthop_ip_edge_cases(self):
        """Test RouteSpec.from_nexthop_ip with edge case IP addresses."""
        svm_name = "os-550e8400-e29b-41d4-a716-446655440000"

        # Edge cases for third octet = 0 within 100.64.0.0/10 subnet
        edge_cases_zero = [
            "100.64.0.1",
            "100.127.0.1",
            "100.65.0.1",
        ]

        for ip in edge_cases_zero:
            spec = RouteSpec.from_nexthop_ip(svm_name, ip)
            assert spec.destination == ipaddress.IPv4Network("100.126.0.0/17")
            assert str(spec.gateway) == ip

        # Edge cases for third octet = 128 within 100.64.0.0/10 subnet
        edge_cases_128 = [
            "100.64.128.1",
            "100.127.128.255",
            "100.65.128.1",
        ]

        for ip in edge_cases_128:
            spec = RouteSpec.from_nexthop_ip(svm_name, ip)
            assert spec.destination == ipaddress.IPv4Network("100.126.128.0/17")
            assert str(spec.gateway) == ip

    def test_calculate_destination_boundary_values(self):
        """Test _calculate_destination with boundary values for third octet."""
        # Test exact boundary values within 100.64.0.0/10 subnet
        assert RouteSpec._calculate_destination("100.64.0.1") == ipaddress.IPv4Network(
            "100.126.0.0/17"
        )
        assert RouteSpec._calculate_destination(
            "100.64.128.1"
        ) == ipaddress.IPv4Network("100.126.128.0/17")

        # Test values just outside boundaries should fail
        with pytest.raises(ValueError, match="Unsupported IP pattern"):
            RouteSpec._calculate_destination("100.64.1.1")  # Just above 0

        with pytest.raises(ValueError, match="Unsupported IP pattern"):
            RouteSpec._calculate_destination("100.64.127.1")  # Just below 128

        with pytest.raises(ValueError, match="Unsupported IP pattern"):
            RouteSpec._calculate_destination("100.64.129.1")  # Just above 128

    def test_calculate_destination_subnet_validation(self):
        """Test _calculate_destination validates IP is within 100.64.0.0/10 subnet."""
        # Test IPs outside 100.64.0.0/10 subnet should fail
        invalid_subnet_ips = [
            "192.168.0.1",  # Private network
            "10.0.0.1",  # Private network
            "172.16.0.1",  # Private network
            "8.8.8.8",  # Public network
            "100.63.0.1",  # Just below 100.64.0.0/10
            "100.128.0.1",  # Just above 100.64.0.0/10
            "101.64.0.1",  # Outside range
            "99.64.0.1",  # Outside range
        ]

        for invalid_ip in invalid_subnet_ips:
            with pytest.raises(ValueError, match="not within required 100.64.0.0/10"):
                RouteSpec._calculate_destination(invalid_ip)

    def test_from_nexthop_ip_subnet_validation(self):
        """Test RouteSpec.from_nexthop_ip validates IP is within 100.64.0.0/10."""
        svm_name = "os-550e8400-e29b-41d4-a716-446655440000"

        # Test IPs outside 100.64.0.0/10 subnet should fail
        invalid_subnet_ips = [
            "192.168.0.1",  # Private network
            "10.0.0.1",  # Private network
            "172.16.128.1",  # Private network
            "8.8.8.8",  # Public network
            "100.63.0.1",  # Just below 100.64.0.0/10
            "100.128.0.1",  # Just above 100.64.0.0/10
        ]

        for invalid_ip in invalid_subnet_ips:
            with pytest.raises(ValueError, match="not within required 100.64.0.0/10"):
                RouteSpec.from_nexthop_ip(svm_name, invalid_ip)

    def test_calculate_destination_valid_subnet_range(self):
        """Test _calculate_destination accepts valid IPs within 100.64.0.0/10 subnet."""
        # Test boundary IPs within 100.64.0.0/10 subnet
        valid_subnet_ips = [
            (
                "100.64.0.1",
                ipaddress.IPv4Network("100.126.0.0/17"),
            ),  # Start of range, third octet 0
            (
                "100.64.128.1",
                ipaddress.IPv4Network("100.126.128.0/17"),
            ),  # Start of range, third octet 128
            (
                "100.127.0.1",
                ipaddress.IPv4Network("100.126.0.0/17"),
            ),  # End of range, third octet 0
            (
                "100.127.128.1",
                ipaddress.IPv4Network("100.126.128.0/17"),
            ),  # End of range, third octet 128
            (
                "100.65.0.100",
                ipaddress.IPv4Network("100.126.0.0/17"),
            ),  # Middle of range, third octet 0
            (
                "100.66.128.200",
                ipaddress.IPv4Network("100.126.128.0/17"),
            ),  # Middle of range, third octet 128
        ]

        for valid_ip, expected_destination in valid_subnet_ips:
            destination = RouteSpec._calculate_destination(valid_ip)
            assert destination == expected_destination

    def test_route_spec_invalid_gateway_ip(self):
        """Test route specification with gateway IP outside carrier-grade NAT range."""
        from pydantic import ValidationError

        invalid_gateways = [
            "192.168.1.1",  # Private network
            "10.0.0.1",  # Private network
            "8.8.8.8",  # Public network
            "100.63.0.1",  # Just below 100.64.0.0/10
            "100.128.0.1",  # Just above 100.64.0.0/10
        ]

        for invalid_gateway in invalid_gateways:
            with pytest.raises(ValidationError):
                RouteSpec(
                    svm_name="os-test-project",
                    gateway=invalid_gateway,
                    destination="100.126.0.0/17",
                )


class TestRouteResult:
    """Test cases for RouteResult value object."""

    def test_valid_route_result(self):
        """Test creating a valid route result."""
        result = RouteResult(
            uuid="route-uuid-123",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
            svm_name="os-test-project",
        )

        assert result.uuid == "route-uuid-123"
        assert result.gateway == "100.127.0.17"
        assert result.destination == ipaddress.IPv4Network("100.126.0.0/17")
        assert result.svm_name == "os-test-project"

    def test_route_result_immutable(self):
        """Test that route result is immutable."""
        result = RouteResult(
            uuid="route-uuid-123",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
            svm_name="os-test-project",
        )

        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            result.uuid = "new-uuid"  # type: ignore[misc]

    def test_route_result_various_destinations(self):
        """Test route result with various destination formats."""
        destinations = [
            ipaddress.IPv4Network("100.126.0.0/17"),
            ipaddress.IPv4Network("100.126.128.0/17"),
            ipaddress.IPv4Network("192.168.1.0/24"),
            ipaddress.IPv4Network("10.0.0.0/8"),
            ipaddress.IPv4Network("0.0.0.0/0"),
        ]

        for destination in destinations:
            result = RouteResult(
                uuid="route-uuid-123",
                gateway="100.127.0.17",
                destination=destination,
                svm_name="os-test-project",
            )
            assert result.destination == destination

    def test_route_result_pydantic_serialization(self):
        """Test Pydantic serialization and deserialization of RouteResult."""
        result = RouteResult(
            uuid="route-uuid-123",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
            svm_name="os-test-project"
        )

        # Test JSON serialization
        json_data = result.model_dump_json()
        assert '"uuid":"route-uuid-123"' in json_data
        assert '"gateway":"100.127.0.17"' in json_data
        assert '"destination":"100.126.0.0/17"' in json_data
        assert '"svm_name":"os-test-project"' in json_data

        # Test dictionary serialization (mode='json' converts IPv4Network to string)
        dict_data = result.model_dump(mode='json')
        expected_dict = {
            "uuid": "route-uuid-123",
            "gateway": "100.127.0.17",
            "destination": "100.126.0.0/17",
            "svm_name": "os-test-project"
        }
        assert dict_data == expected_dict

        # Test deserialization from dictionary
        recreated_result = RouteResult.model_validate(dict_data)
        assert recreated_result.uuid == result.uuid
        assert recreated_result.gateway == result.gateway
        assert str(recreated_result.destination) == str(result.destination)
        assert recreated_result.svm_name == result.svm_name

    def test_route_result_ip_network_validation(self):
        """Test IPv4Network validation for RouteResult destination field."""
        # Test valid network
        result = RouteResult(
            uuid="route-uuid-123",
            gateway="100.127.0.17",
            destination="192.168.1.0/24",
            svm_name="os-test-project"
        )
        assert str(result.destination) == "192.168.1.0/24"

        # Test that string networks are accepted (backward compatibility)
        result_str = RouteResult(
            uuid="route-uuid-123",
            gateway="100.127.0.17",
            destination="invalid-network",  # This is now allowed as a string
            svm_name="os-test-project"
        )
        assert result_str.destination == "invalid-network"
