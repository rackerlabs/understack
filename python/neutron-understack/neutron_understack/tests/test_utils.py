from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from neutron.plugins.ml2.driver_context import portbindings
from neutron_lib import constants
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from neutron_understack import utils


class TestParentPortIsBound:
    def test_truthy_conditions(self, port_object):
        """Truthy conditions.

        When vif type is "other", vnic_type is "baremetal"
        and binding profile is present.
        """
        result = utils.parent_port_is_bound(port_object)
        assert result is True

    def test_vif_type_unbound(self, port_object):
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        result = utils.parent_port_is_bound(port_object)
        assert result is False

    def test_vnic_type_normal(self, port_object):
        port_object.bindings[0].vnic_type = portbindings.VNIC_NORMAL
        result = utils.parent_port_is_bound(port_object)
        assert result is False

    def test_no_binding_profile(self, port_object):
        port_object.bindings[0].profile = {}
        result = utils.parent_port_is_bound(port_object)
        assert result is False


Base = declarative_base()


class Port(Base):
    __tablename__ = "ports"
    id = Column(String, primary_key=True)
    device_id = Column(String)
    device_owner = Column(String)


@pytest.fixture(scope="function")
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = scoped_session(sessionmaker(bind=engine))
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def sample_port(db_session):
    port = Port(id="port-1", device_id="original", device_owner="owner")
    db_session.add(port)
    db_session.commit()
    return port


@pytest.fixture
def mock_get_admin_context(db_session):
    class Context:
        session = db_session

    with patch("neutron_lib.context.get_admin_context", return_value=Context()):
        yield


class TestPortFieldManipulation:
    def test_update_port_fields_updates_fields(
        self, db_session, mock_get_admin_context, sample_port
    ):
        id = sample_port.id
        utils.update_port_fields(id, {"device_id": "new-id"})
        port = db_session.query(Port).filter_by(id=id).one()
        assert port.device_id == "new-id"
        assert port.device_owner == "owner"

    def test_clear_device_id_for_port(
        self, db_session, mock_get_admin_context, sample_port
    ):
        id = sample_port.id
        utils.clear_device_id_for_port(id)
        port = db_session.query(Port).filter_by(id=id).one()
        assert port.device_id == ""

    def test_set_device_id_and_owner_for_port(
        self, db_session, mock_get_admin_context, sample_port
    ):
        id = sample_port.id
        utils.set_device_id_and_owner_for_port(id, "dev-2", "own-2")
        port = db_session.query(Port).filter_by(id=id).one()
        assert port.device_id == "dev-2"
        assert port.device_owner == "own-2"


class PortContext:
    def __init__(self, current):
        self.current = current


class TestIsRouterInterface:
    def test_router_interface_true(self):
        context = PortContext(
            current={"device_owner": constants.DEVICE_OWNER_ROUTER_INTF}
        )
        assert utils.is_router_interface(context)

    def test_router_interface_false_different_device_owner(self):
        context = PortContext(current={"device_owner": "compute:nova"})
        assert not utils.is_router_interface(context)

    def test_router_interface_false_device_owner_missing(self):
        context = PortContext(current={})
        with pytest.raises(KeyError):
            utils.is_router_interface(context)

    def test_router_interface_false_device_owner_none(self):
        context = PortContext(current={"device_owner": None})
        assert not utils.is_router_interface(context)


class TestMergeOverlappedRanges:
    def test_single_range(self):
        assert utils.merge_overlapped_ranges([(1, 5)]) == [(1, 5)]

    def test_no_overlap(self):
        ranges = [(1, 3), (5, 7), (9, 10)]
        expected = [(1, 3), (5, 7), (9, 10)]
        assert utils.merge_overlapped_ranges(ranges) == expected

    def test_simple_overlap(self):
        ranges = [(1, 4), (2, 5)]
        expected = [(1, 5)]
        assert utils.merge_overlapped_ranges(ranges) == expected

    def test_multiple_ranges(self):
        ranges = [(1, 3), (2, 6), (8, 10), (15, 18)]
        expected = [(1, 6), (8, 10), (15, 18)]
        assert utils.merge_overlapped_ranges(ranges) == expected

    def test_touching_ranges(self):
        ranges = [(1, 4), (5, 7), (8, 10)]
        expected = [(1, 10)]
        assert utils.merge_overlapped_ranges(ranges) == expected

    def test_unsorted_input(self):
        ranges = [(8, 10), (1, 3), (2, 7), (15, 18)]
        expected = [(1, 10), (15, 18)]
        assert utils.merge_overlapped_ranges(ranges) == expected


class TestFetchGapsInRanges:
    def test_full_coverage(self):
        assert utils.fetch_gaps_in_ranges([(1, 10)], (1, 10)) == []

    def test_gap_at_start(self):
        assert utils.fetch_gaps_in_ranges([(5, 8)], (1, 10)) == [(1, 4), (9, 10)]

    def test_gap_at_end(self):
        assert utils.fetch_gaps_in_ranges([(1, 6)], (1, 10)) == [(7, 10)]

    def test_gap_in_middle(self):
        assert utils.fetch_gaps_in_ranges([(1, 2), (5, 10)], (1, 10)) == [(3, 4)]

    def test_multiple_gaps(self):
        result = utils.fetch_gaps_in_ranges([(1, 2), (4, 5), (8, 8)], (1, 10))
        assert result == [(3, 3), (6, 7), (9, 10)]


class DummyRange:
    def __init__(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum


class TestAllowedTenantVlanIdRanges:
    def test_multiple_non_overlapping_ranges(
        self,
        mocker,
        oslo_config,
    ):
        oslo_config.config(
            default_tenant_vlan_id_range=[1, 2000],
            group="ml2_understack",
        )
        mocker.patch(
            "neutron_understack.utils.fetch_vlan_network_segment_ranges",
            return_value=[DummyRange(500, 700), DummyRange(900, 1200)],
        )
        expected_result = [(1, 499), (701, 899), (1201, 2000)]
        result = utils.allowed_tenant_vlan_id_ranges()
        assert result == expected_result

    def test_multiple_overlapping_ranges(
        self,
        mocker,
        oslo_config,
    ):
        oslo_config.config(
            default_tenant_vlan_id_range=[1, 2000],
            group="ml2_understack",
        )
        mocker.patch(
            "neutron_understack.utils.fetch_vlan_network_segment_ranges",
            return_value=[DummyRange(500, 700), DummyRange(600, 1200)],
        )
        expected_result = [(1, 499), (1201, 2000)]
        result = utils.allowed_tenant_vlan_id_ranges()
        assert result == expected_result

    def test_single_range(
        self,
        mocker,
        oslo_config,
    ):
        oslo_config.config(
            default_tenant_vlan_id_range=[1, 2000],
            group="ml2_understack",
        )
        mocker.patch(
            "neutron_understack.utils.fetch_vlan_network_segment_ranges",
            return_value=[DummyRange(500, 700)],
        )
        expected_result = [(1, 499), (701, 2000)]
        result = utils.allowed_tenant_vlan_id_ranges()
        assert result == expected_result


class TestIsUuid:
    def test_valid_uuid(self):
        assert utils._is_uuid("7ca98881-bca5-4c82-9369-66eb36292a95") is True

    def test_invalid_uuid(self):
        assert utils._is_uuid("not-a-uuid") is False

    def test_hostname(self):
        assert utils._is_uuid("1327172-hp1") is False

    def test_empty_string(self):
        assert utils._is_uuid("") is False


class TestFetchNetworkNodeTrunkId:
    @pytest.fixture(autouse=True)
    def reset_cache(self):
        """Reset the cache before each test."""
        utils._cached_network_node_trunk_id = None
        yield
        utils._cached_network_node_trunk_id = None

    def test_successful_discovery_with_hostname(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

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

        result = utils.fetch_network_node_trunk_id()

        assert result == "trunk-456"
        assert utils._cached_network_node_trunk_id == "trunk-456"
        mock_ironic.baremetal_node_uuid.assert_called_once_with("gateway-host-1")

    def test_successful_discovery_with_uuid(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

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

        result = utils.fetch_network_node_trunk_id()

        assert result == "trunk-456"
        mock_ironic.baremetal_node_name.assert_called_once_with(gateway_uuid)
        mock_ironic.baremetal_node_uuid.assert_not_called()

    def test_cache_returns_cached_value(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

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
        result1 = utils.fetch_network_node_trunk_id()
        assert result1 == "trunk-456"

        # Second call should use cache
        result2 = utils.fetch_network_node_trunk_id()
        assert result2 == "trunk-456"

        assert mock_get_bindings.call_count == 2

    def test_no_gateway_agents_found(self, mocker):
        """Test exception when no alive gateway agents found."""
        mock_context = MagicMock()
        mock_plugin = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch(
            "neutron_lib.plugins.directory.get_plugin", return_value=mock_plugin
        )

        mock_plugin.get_agents.return_value = []

        with pytest.raises(Exception, match="No alive OVN Controller Gateway agents"):
            utils.fetch_network_node_trunk_id()

    def test_no_core_plugin(self, mocker):
        """Test exception when core plugin is not available."""
        mock_context = MagicMock()

        mocker.patch("neutron_lib.context.get_admin_context", return_value=mock_context)
        mocker.patch("neutron_lib.plugins.directory.get_plugin", return_value=None)

        with pytest.raises(Exception, match="Unable to obtain core plugin"):
            utils.fetch_network_node_trunk_id()

    def test_ironic_resolution_fails_uuid_to_hostname(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

        with pytest.raises(Exception, match="Failed to resolve baremetal node UUID"):
            utils.fetch_network_node_trunk_id()

    def test_ironic_resolution_fails_hostname_to_uuid(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

        with pytest.raises(Exception, match="Failed to resolve hostname"):
            utils.fetch_network_node_trunk_id()

    def test_no_ports_bound_to_gateway(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

        # Mock no port bindings found for gateway hosts
        mocker.patch("neutron.objects.ports.PortBinding.get_objects", return_value=[])

        with pytest.raises(Exception, match="No ports found bound to gateway hosts"):
            utils.fetch_network_node_trunk_id()

    def test_no_trunk_found(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

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
            utils.fetch_network_node_trunk_id()

    def test_port_bound_to_resolved_hostname(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

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

        result = utils.fetch_network_node_trunk_id()

        assert result == "trunk-456"

    def test_port_bound_to_uuid_when_agent_reports_hostname(self, mocker):
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
        mocker.patch("neutron_understack.utils.IronicClient", return_value=mock_ironic)

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

        result = utils.fetch_network_node_trunk_id()

        assert result == "trunk-456"
        mock_ironic.baremetal_node_uuid.assert_called_once_with("gateway-host-1")
