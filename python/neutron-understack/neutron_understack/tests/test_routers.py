import pytest
from neutron_lib import constants as p_const

from neutron_understack.routers import add_subport_to_trunk
from neutron_understack.routers import create_port_postcommit
from neutron_understack.routers import fetch_or_create_router_segment
from neutron_understack.routers import handle_router_interface_removal
from neutron_understack.routers import handle_subport_removal


class TestFetchOrCreateRouterSegment:
    def test_when_successful(self, mocker, port_context, network_id):
        fake_segment = {"id": "seg-123", "foo": "bar"}
        fake_physnet = "fake-physnet"
        port_context.current["network_id"] = str(network_id)

        mock_alloc = mocker.patch(
            "neutron_understack.utils.allocate_dynamic_segment",
            return_value=fake_segment,
        )
        mocker.patch(
            "oslo_config.cfg.CONF.ml2_understack.network_node_switchport_physnet",
            fake_physnet,
        )
        result = fetch_or_create_router_segment(port_context)

        mock_alloc.assert_called_once_with(
            network_id=str(network_id),
            physnet=fake_physnet,
        )
        assert result is fake_segment


class TestAddSubportToTrunk:
    def test_when_successful(self, mocker):
        trunk_id = "trunk-uuid"
        port = {"id": "port-123"}
        segment = {"segmentation_id": 42}
        mocker.patch(
            "neutron_understack.network_node_trunk.fetch_network_node_trunk_id",
            return_value=trunk_id,
        )
        mocker.patch(
            "neutron_lib.context.get_admin_context", return_value="admin_context"
        )

        mock_trunk_plugin = mocker.Mock()
        mocker.patch(
            "neutron_understack.utils.fetch_trunk_plugin",
            return_value=mock_trunk_plugin,
        )

        add_subport_to_trunk(port, segment)

        mock_trunk_plugin.add_subports.assert_called_once_with(
            context="admin_context",
            trunk_id=trunk_id,
            subports={
                "sub_ports": [
                    {
                        "port_id": port["id"],
                        "segmentation_id": 42,
                        "segmentation_type": p_const.TYPE_VLAN,
                    }
                ]
            },
        )


class TestHandleSubportRemoval:
    def test_when_successful(self, mocker, port_id, trunk_id):
        mocker.patch(
            "neutron_understack.network_node_trunk.fetch_network_node_trunk_id",
            return_value=str(trunk_id),
        )
        mock_remove = mocker.patch("neutron_understack.utils.remove_subport_from_trunk")
        port = {"id": str(port_id)}
        handle_subport_removal(port)
        mock_remove.assert_called_once_with(str(trunk_id), str(port_id))


class TestHandleRouterInterfaceRemoval:
    def test_case_for_non_router(self, mocker, port_db_payload):
        mock_sb_removal = mocker.patch(
            "neutron_understack.routers.handle_subport_removal"
        )
        mock_localnet_removal = mocker.patch(
            "neutron_understack.routers.delete_uplink_port"
        )

        port_db_payload.metadata["port_db"].device_owner = "not_a_router"

        handle_router_interface_removal(None, None, None, port_db_payload)

        mock_sb_removal.assert_not_called()
        mock_localnet_removal.assert_not_called()

    def test_when_network_in_use(self, mocker, port_db_payload):
        mock_sb_removal = mocker.patch(
            "neutron_understack.routers.handle_subport_removal"
        )
        mock_localnet_removal = mocker.patch(
            "neutron_understack.routers.delete_uplink_port"
        )
        mocker.patch(
            "neutron_understack.routers.is_only_router_port_on_network",
            return_value=False,
        )

        handle_router_interface_removal(None, None, None, port_db_payload)

        mock_sb_removal.assert_not_called()
        mock_localnet_removal.assert_not_called()

    def test_last_port_on_network(
        self, mocker, port_object, port_db_payload, network_id
    ):
        mock_sb_removal = mocker.patch(
            "neutron_understack.routers.handle_subport_removal"
        )
        mock_localnet_removal = mocker.patch(
            "neutron_understack.routers.delete_uplink_port"
        )
        mocker.patch(
            "neutron_understack.routers.is_only_router_port_on_network",
            return_value=True,
        )
        fake_segment = {"id": "seg-123", "foo": "bar"}
        mocker.patch(
            "neutron_understack.routers.fetch_router_network_segment",
            return_value=fake_segment,
        )

        mocker.patch(
            "neutron_understack.routers.fetch_shared_router_port",
            return_value=port_object,
        )
        delete_shared_port = mocker.patch.object(port_object, "delete")

        handle_router_interface_removal(None, None, None, port_db_payload)

        mock_sb_removal.assert_called_once_with(port_object)
        mock_localnet_removal.assert_called_once_with(fake_segment, str(network_id))
        delete_shared_port.assert_called_once()


@pytest.fixture
def context(mocker):
    return mocker.MagicMock(
        current={
            "id": "port123",
            "device_id": "dev456",
            "device_owner": "owner789",
            "network_id": "8ddd659b-b6da-4fa3-bd45-f9c3d25bf209",
        },
        plugin_context="123",
    )


class TestCreatePortPostcommit:
    def test_existing_router_on_network(self, mocker, port_context):
        mocker.patch("neutron.objects.ports.Port.get_objects", return_value=[1, 2])
        add_trunk = mocker.patch("neutron_understack.routers.add_subport_to_trunk")
        create_neutron_port = mocker.patch(
            "neutron_understack.utils.create_neutron_port_for_segment"
        )
        create_uplink_port = mocker.patch(
            "neutron_understack.routers.create_uplink_port"
        )

        create_port_postcommit(port_context)
        create_neutron_port.assert_not_called()
        add_trunk.assert_not_called()
        create_uplink_port.assert_not_called()

    def test_no_router_on_network(self, mocker, port_context):
        mocker.patch("neutron.objects.ports.Port.get_objects", return_value=[])
        fake_segment = {"id": "seg-123", "foo": "bar"}
        create_segment = mocker.patch(
            "neutron_understack.routers.fetch_or_create_router_segment",
            return_value=fake_segment,
        )
        port = {"id": "port-123"}
        create_neutron_port = mocker.patch(
            "neutron_understack.utils.create_neutron_port_for_segment",
            return_value=port,
        )
        add_trunk = mocker.patch("neutron_understack.routers.add_subport_to_trunk")
        fetch_segment_obj = mocker.patch(
            "neutron_understack.utils.network_segment_by_id", return_value=fake_segment
        )
        create_uplink_port = mocker.patch(
            "neutron_understack.routers.create_uplink_port"
        )

        create_port_postcommit(port_context)

        create_segment.assert_called_once_with(port_context)
        create_neutron_port.assert_called_once_with(fake_segment, port_context)
        add_trunk.assert_called_once_with(port, fake_segment)
        fetch_segment_obj.assert_called_once_with(fake_segment["id"])
        create_uplink_port.assert_called_once_with(
            fake_segment, port_context.current["network_id"]
        )
