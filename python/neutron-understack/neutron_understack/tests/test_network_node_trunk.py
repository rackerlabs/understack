"""Tests for network_node_trunk module."""

from unittest.mock import MagicMock

import pytest

from neutron_understack import network_node_trunk


class TestFetchNetworkNodeTrunkId:
    """Tests for fetch_network_node_trunk_id function."""

    @pytest.fixture(autouse=True)
    def reset_cache(self) -> None:
        """Reset the cache before each test."""
        network_node_trunk._cached_network_node_trunk_id = None
        yield
        network_node_trunk._cached_network_node_trunk_id = None

    def test_successful_discovery_with_hostname(self, mocker) -> None:
        """Test successful trunk discovery when gateway host is a hostname."""
        # Mock context and plugin
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        # Mock gateway agent with hostname
        mock_plugin.get_agents.return_value = [
            {"host": "gateway-host-1", "id": "agent-1"}
        ]

        # Mock Ironic client to resolve hostname to UUID
        gateway_uuid = "7ca98881-bca5-4c82-9369-66eb36292a95"
        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_uuid.return_value = gateway_uuid
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        # Mock port binding
        mock_binding = MagicMock()
        mock_binding.port_id = "port-123"
        mock_binding.host = "gateway-host-1"
        mocker.patch(
            "neutron.objects.ports.PortBinding.get_objects",
            return_value=[mock_binding],
        )

        # Mock port
        mock_port = MagicMock()
        mock_port.id = "port-123"
        mocker.patch("neutron.objects.ports.Port.get_object", return_value=mock_port)

        # Mock trunk
        mock_trunk = MagicMock()
        mock_trunk.id = "trunk-456"
        mock_trunk.port_id = "port-123"

        mocker.patch(
            "neutron.objects.trunk.Trunk.get_objects", return_value=[mock_trunk]
        )

        result = network_node_trunk.fetch_network_node_trunk_id()

        assert result == "trunk-456"
        assert network_node_trunk._cached_network_node_trunk_id == "trunk-456"
        mock_ironic.baremetal_node_uuid.assert_called_once_with("gateway-host-1")

    def test_successful_discovery_with_uuid(self, mocker) -> None:
        """Test successful trunk discovery when gateway host is a UUID."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        # Mock gateway agent with UUID
        gateway_uuid = "7ca98881-bca5-4c82-9369-66eb36292a95"
        mock_plugin.get_agents.return_value = [{"host": gateway_uuid, "id": "agent-1"}]

        # Mock Ironic client to resolve UUID to hostname
        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_name.return_value = "gateway-host-1"
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        # Mock port binding bound to UUID
        mock_binding = MagicMock()
        mock_binding.port_id = "port-123"
        mock_binding.host = gateway_uuid
        mocker.patch(
            "neutron.objects.ports.PortBinding.get_objects",
            return_value=[mock_binding],
        )

        # Mock port
        mock_port = MagicMock()
        mock_port.id = "port-123"
        mocker.patch("neutron.objects.ports.Port.get_object", return_value=mock_port)

        # Mock trunk
        mock_trunk = MagicMock()
        mock_trunk.id = "trunk-456"
        mock_trunk.port_id = "port-123"

        mocker.patch(
            "neutron.objects.trunk.Trunk.get_objects", return_value=[mock_trunk]
        )

        result = network_node_trunk.fetch_network_node_trunk_id()

        assert result == "trunk-456"
        mock_ironic.baremetal_node_name.assert_called_once_with(gateway_uuid)
        mock_ironic.baremetal_node_uuid.assert_not_called()

    def test_cache_returns_cached_value(self, mocker) -> None:
        """Test that subsequent calls return cached value without querying."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        mock_plugin.get_agents.return_value = [
            {"host": "gateway-host-1", "id": "agent-1"}
        ]

        # Mock Ironic client
        gateway_uuid = "7ca98881-bca5-4c82-9369-66eb36292a95"
        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_uuid.return_value = gateway_uuid
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        # Mock port binding
        mock_binding = MagicMock()
        mock_binding.port_id = "port-123"
        mock_binding.host = "gateway-host-1"
        mock_get_bindings = mocker.patch(
            "neutron.objects.ports.PortBinding.get_objects",
            return_value=[mock_binding],
        )

        # Mock port
        mock_port = MagicMock()
        mock_port.id = "port-123"
        mocker.patch("neutron.objects.ports.Port.get_object", return_value=mock_port)

        mock_trunk = MagicMock()
        mock_trunk.id = "trunk-456"
        mock_trunk.port_id = "port-123"

        mocker.patch(
            "neutron.objects.trunk.Trunk.get_objects", return_value=[mock_trunk]
        )

        # First call
        result1 = network_node_trunk.fetch_network_node_trunk_id()
        assert result1 == "trunk-456"

        # Second call should use cache
        result2 = network_node_trunk.fetch_network_node_trunk_id()
        assert result2 == "trunk-456"

        assert mock_get_bindings.call_count == 2

    def test_no_gateway_agents_found(self, mocker) -> None:
        """Test exception when no alive gateway agents found."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        mock_plugin.get_agents.return_value = []

        with pytest.raises(Exception, match="No alive OVN Controller Gateway agents"):
            network_node_trunk.fetch_network_node_trunk_id()

    def test_no_core_plugin(self, mocker) -> None:
        """Test exception when core plugin is not available."""
        mock_context = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch("neutron_lib.plugins.directory.get_plugin", return_value=None)

        with pytest.raises(Exception, match="Unable to obtain core plugin"):
            network_node_trunk.fetch_network_node_trunk_id()

    def test_ironic_resolution_fails_uuid_to_hostname(self, mocker) -> None:
        """Test exception when Ironic fails to resolve UUID to hostname."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        gateway_uuid = "7ca98881-bca5-4c82-9369-66eb36292a95"
        mock_plugin.get_agents.return_value = [{"host": gateway_uuid, "id": "agent-1"}]

        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_name.return_value = None
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        with pytest.raises(Exception, match="Failed to resolve baremetal node UUID"):
            network_node_trunk.fetch_network_node_trunk_id()

    def test_ironic_resolution_fails_hostname_to_uuid(self, mocker) -> None:
        """Test exception when Ironic fails to resolve hostname to UUID."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        mock_plugin.get_agents.return_value = [
            {"host": "gateway-host-1", "id": "agent-1"}
        ]

        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_uuid.return_value = None
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        with pytest.raises(Exception, match="Failed to resolve hostname"):
            network_node_trunk.fetch_network_node_trunk_id()

    def test_no_ports_bound_to_gateway(self, mocker) -> None:
        """Test exception when no ports are bound to gateway host."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        mock_plugin.get_agents.return_value = [
            {"host": "gateway-host-1", "id": "agent-1"}
        ]

        # Mock Ironic client
        gateway_uuid = "7ca98881-bca5-4c82-9369-66eb36292a95"
        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_uuid.return_value = gateway_uuid
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        # Mock no port bindings found for gateway hosts
        mocker.patch("neutron.objects.ports.PortBinding.get_objects", return_value=[])

        with pytest.raises(Exception, match="No ports found bound to gateway hosts"):
            network_node_trunk.fetch_network_node_trunk_id()

    def test_no_trunk_found(self, mocker) -> None:
        """Test exception when no trunk matches gateway ports."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        mock_plugin.get_agents.return_value = [
            {"host": "gateway-host-1", "id": "agent-1"}
        ]

        # Mock Ironic client
        gateway_uuid = "7ca98881-bca5-4c82-9369-66eb36292a95"
        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_uuid.return_value = gateway_uuid
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        # Mock port binding
        mock_binding = MagicMock()
        mock_binding.port_id = "port-123"
        mock_binding.host = "gateway-host-1"
        mocker.patch(
            "neutron.objects.ports.PortBinding.get_objects",
            return_value=[mock_binding],
        )

        # Mock port
        mock_port = MagicMock()
        mock_port.id = "port-123"
        mocker.patch("neutron.objects.ports.Port.get_object", return_value=mock_port)

        # Mock trunk with different parent port
        mock_trunk = MagicMock()
        mock_trunk.id = "trunk-456"
        mock_trunk.port_id = "different-port"

        mocker.patch(
            "neutron.objects.trunk.Trunk.get_objects", return_value=[mock_trunk]
        )

        with pytest.raises(Exception, match="Unable to find network node trunk"):
            network_node_trunk.fetch_network_node_trunk_id()

    def test_port_bound_to_resolved_hostname(self, mocker) -> None:
        """Test when port is bound to resolved hostname instead of UUID."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        gateway_uuid = "7ca98881-bca5-4c82-9369-66eb36292a95"
        mock_plugin.get_agents.return_value = [{"host": gateway_uuid, "id": "agent-1"}]

        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_name.return_value = "gateway-host-1"
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        # Port binding bound to hostname, not UUID
        mock_binding = MagicMock()
        mock_binding.port_id = "port-123"
        mock_binding.host = "gateway-host-1"
        mocker.patch(
            "neutron.objects.ports.PortBinding.get_objects",
            return_value=[mock_binding],
        )

        # Mock port
        mock_port = MagicMock()
        mock_port.id = "port-123"
        mocker.patch("neutron.objects.ports.Port.get_object", return_value=mock_port)

        mock_trunk = MagicMock()
        mock_trunk.id = "trunk-456"
        mock_trunk.port_id = "port-123"

        mocker.patch(
            "neutron.objects.trunk.Trunk.get_objects", return_value=[mock_trunk]
        )

        result = network_node_trunk.fetch_network_node_trunk_id()

        assert result == "trunk-456"

    def test_port_bound_to_uuid_when_agent_reports_hostname(self, mocker) -> None:
        """Test when agent reports hostname but port is bound to UUID."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        # Agent reports hostname
        mock_plugin.get_agents.return_value = [
            {"host": "gateway-host-1", "id": "agent-1"}
        ]

        # Ironic resolves hostname to UUID
        gateway_uuid = "7ca98881-bca5-4c82-9369-66eb36292a95"
        mock_ironic = MagicMock()
        mock_ironic.baremetal_node_uuid.return_value = gateway_uuid
        mocker.patch(
            "neutron_understack.network_node_trunk.IronicClient",
            return_value=mock_ironic,
        )

        # Port binding bound to UUID, not hostname
        mock_binding = MagicMock()
        mock_binding.port_id = "port-123"
        mock_binding.host = gateway_uuid
        mocker.patch(
            "neutron.objects.ports.PortBinding.get_objects",
            return_value=[mock_binding],
        )

        # Mock port
        mock_port = MagicMock()
        mock_port.id = "port-123"
        mocker.patch("neutron.objects.ports.Port.get_object", return_value=mock_port)

        mock_trunk = MagicMock()
        mock_trunk.id = "trunk-456"
        mock_trunk.port_id = "port-123"

        mocker.patch(
            "neutron.objects.trunk.Trunk.get_objects", return_value=[mock_trunk]
        )

        result = network_node_trunk.fetch_network_node_trunk_id()

        assert result == "trunk-456"
        mock_ironic.baremetal_node_uuid.assert_called_once_with("gateway-host-1")
