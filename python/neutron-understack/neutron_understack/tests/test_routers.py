from uuid import uuid4

import pytest
from neutron_lib import constants as p_const

from neutron_understack.routers import add_subport_to_trunk
from neutron_understack.routers import create_router_segment
from neutron_understack.routers import events
from neutron_understack.routers import resources


@pytest.fixture
def port_context(mocker):
    fake_id = str(uuid4())
    ctx = mocker.Mock()
    ctx.current = {"network_id": fake_id}
    return ctx, fake_id


def test_create_router_segment_calls(mocker, port_context):
    ctx, fake_id = port_context
    fake_segment = {"id": "seg-123", "foo": "bar"}
    fake_segment_obj = mocker.Mock(id="seg-123")
    fake_physnet = "fake-physnet"

    mock_alloc = mocker.patch(
        "neutron_understack.utils.allocate_dynamic_segment", return_value=fake_segment
    )
    mock_byid = mocker.patch(
        "neutron_understack.utils.network_segment_by_id", return_value=fake_segment_obj
    )
    mock_publish = mocker.patch("neutron_lib.callbacks.registry.publish")
    mock_payload = mocker.patch(
        "neutron_lib.callbacks.events.DBEventPayload",
        side_effect=lambda *a, **k: "somepayload",
    )
    mocker.patch(
        "oslo_config.cfg.CONF.ml2_understack.network_node_switchport_physnet",
        fake_physnet,
    )

    driver = mocker.Mock(create_port_postcommit="postcommit_func")

    result = create_router_segment(driver, ctx)

    mock_alloc.assert_called_once_with(
        network_id=str(fake_id),
        physnet=fake_physnet,
    )
    mock_byid.assert_called_once_with("seg-123")
    args, kwargs = mock_publish.call_args
    assert args[0] == resources.SEGMENT
    assert args[1] == events.AFTER_CREATE
    assert args[2] == "postcommit_func"
    assert kwargs["payload"] == "somepayload"
    mock_payload.assert_called_once_with(
        ctx, resource_id="seg-123", states=(fake_segment_obj,)
    )
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


def test_handle_router_interface_removal(mocker):
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
    payload = mocker.Mock(metadata={"port": port})

    from neutron_understack.routers import handle_router_interface_removal

    handle_router_interface_removal(None, None, None, payload)

    mock_remove.assert_called_once_with(trunk_id, port_id)
