from uuid import uuid4

import pytest
from neutron_lib import constants as p_const

from neutron_understack.routers import _handle_subport_removal
from neutron_understack.routers import add_subport_to_trunk
from neutron_understack.routers import create_port_postcommit
from neutron_understack.routers import create_router_segment
from neutron_understack.routers import handle_router_interface_removal


@pytest.fixture
def port_context(mocker):
    fake_id = str(uuid4())
    ctx = mocker.Mock()
    ctx.current = {"network_id": fake_id}
    return ctx, fake_id


@pytest.fixture
def ovs_settings(mocker):
    mocker.patch(
        "neutron.conf.agent.ovs_conf.get_igmp_flood_reports", return_value="true"
    )
    mocker.patch("neutron.conf.agent.ovs_conf.get_igmp_flood", return_value="true")


def test_create_router_segment_calls(mocker, port_context, ovs_settings):
    ctx, fake_id = port_context
    fake_segment = {"id": "seg-123", "foo": "bar"}
    fake_physnet = "fake-physnet"

    mock_alloc = mocker.patch(
        "neutron_understack.utils.allocate_dynamic_segment", return_value=fake_segment
    )
    mock_byid = mocker.patch(
        "neutron_understack.utils.network_segment_by_id", return_value=fake_segment
    )
    mock_create_uplink_port = mocker.patch(
        "neutron_understack.routers.create_uplink_port"
    )
    mocker.patch(
        "oslo_config.cfg.CONF.ml2_understack.network_node_switchport_physnet",
        fake_physnet,
    )
    fake_client = mocker.Mock()
    mocker.patch("neutron_understack.routers.ovn_client", return_value=fake_client)

    driver = mocker.Mock(create_port_postcommit="postcommit_func")

    result = create_router_segment(driver, ctx)

    mock_alloc.assert_called_once_with(
        network_id=str(fake_id),
        physnet=fake_physnet,
    )
    mock_byid.assert_called_once_with("seg-123")
    mock_create_uplink_port.assert_called_once_with(fake_segment, port_context[1])
    assert result is fake_segment


@pytest.fixture
def subport_mock_context(mocker):
    class FakePluginContext:
        pass

    return mocker.MagicMock(
        current={"id": "port-123"}, plugin_context=FakePluginContext()
    )


def test_add_subport_to_trunk(mocker, subport_mock_context):
    trunk_id = "trunk-uuid"
    segment = {"segmentation_id": 42}
    mocker.patch(
        "oslo_config.cfg.CONF.ml2_understack.network_node_trunk_uuid",
        trunk_id,
    )

    mock_trunk_plugin = mocker.Mock()
    mocker.patch(
        "neutron_understack.utils.fetch_trunk_plugin", return_value=mock_trunk_plugin
    )

    add_subport_to_trunk(subport_mock_context, segment)

    mock_trunk_plugin.add_subports.assert_called_once_with(
        context=subport_mock_context.plugin_context,
        trunk_id=trunk_id,
        subports={
            "sub_ports": [
                {
                    "port_id": "port-123",
                    "segmentation_id": 42,
                    "segmentation_type": p_const.TYPE_VLAN,
                }
            ]
        },
    )


def test_handle_subport_removal_router(mocker):
    trunk_id = "trunk-uuid"
    port_id = "port-456"
    mocker.patch(
        "oslo_config.cfg.CONF.ml2_understack.network_node_trunk_uuid", trunk_id
    )
    mock_remove = mocker.patch("neutron_understack.utils.remove_subport_from_trunk")
    port = {
        "id": port_id,
        "device_owner": p_const.DEVICE_OWNER_ROUTER_INTF,
    }
    _handle_subport_removal(port)
    mock_remove.assert_called_once_with(trunk_id, port_id)


def test_handle_router_interface_removal_for_non_router(mocker):
    mock_sb_removal = mocker.patch("neutron_understack.routers._handle_subport_removal")
    mock_localnet_removal = mocker.patch(
        "neutron_understack.routers._handle_localnet_port_removal"
    )

    payload = mocker.Mock(metadata={"port": {"device_owner": "not_a_router"}})
    handle_router_interface_removal(None, None, None, payload)

    mock_sb_removal.assert_not_called()
    mock_localnet_removal.assert_not_called()


@pytest.fixture
def context(mocker):
    return mocker.MagicMock(
        current={
            "id": "port123",
            "device_id": "dev456",
            "device_owner": "owner789",
            "network_id": "8ddd659b-b6da-4fa3-bd45-f9c3d25bf209",
        }
    )


@pytest.fixture
def driver(mocker):
    return mocker.MagicMock()


def test_create_port_postcommit_existing_segment(mocker, context, driver):
    segment = {"id": "segmentA"}
    mocker.patch("neutron_lib.context.get_admin_context", return_value=mocker.Mock())
    mocker.patch(
        "neutron.objects.network.NetworkSegment.get_objects", return_value=[segment]
    )
    mock_clear = mocker.patch("neutron_understack.utils.clear_device_id_for_port")
    mock_set_device = mocker.patch(
        "neutron_understack.utils.set_device_id_and_owner_for_port"
    )
    add_trunk = mocker.patch("neutron_understack.routers.add_subport_to_trunk")
    create_router_segment = mocker.patch(
        "neutron_understack.routers.create_router_segment"
    )
    mocker.patch("oslo_config.cfg.ConfigOpts.find_file", return_value=None)
    mocker.patch(
        "oslo_config.cfg.CONF.ml2_understack.network_node_switchport_physnet",
        "x23-1-network",
    )
    create_port_postcommit(context, driver)

    mock_clear.assert_called_once_with("port123")
    add_trunk.assert_called_once_with(context, segment)
    mock_set_device.assert_called_once_with(
        port_id="port123", device_id="dev456", device_owner="owner789"
    )
    create_router_segment.assert_not_called()


def test_segment_creation(mocker, context, driver):
    mock_clear_device_id = mocker.patch(
        "neutron_understack.utils.clear_device_id_for_port"
    )
    mock_set_device_id_and_owner = mocker.patch(
        "neutron_understack.utils.set_device_id_and_owner_for_port"
    )
    mock_add_subport = mocker.patch("neutron_understack.routers.add_subport_to_trunk")
    mock_create_router_segment = mocker.patch(
        "neutron_understack.routers.create_router_segment", return_value="new-seg"
    )
    mocker.patch(
        "oslo_config.cfg.CONF.ml2_understack.network_node_switchport_physnet",
        "x23-1-network",
    )
    mocker.patch("neutron_lib.context.get_admin_context", return_value=mocker.Mock())
    mocker.patch("neutron.objects.network.NetworkSegment.get_objects", return_value=[])

    create_port_postcommit(context, driver)

    mock_create_router_segment.assert_called_once_with(driver, context)
    mock_clear_device_id.assert_called_once_with("port123")
    mock_add_subport.assert_called_once_with(context, "new-seg")
    mock_set_device_id_and_owner.assert_called_once_with(
        port_id="port123", device_id="dev456", device_owner="owner789"
    )
