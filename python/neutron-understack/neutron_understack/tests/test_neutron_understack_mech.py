from unittest.mock import ANY

import pytest
from neutron_lib.api.definitions import portbindings

from neutron_understack import utils
from neutron_understack.nautobot import VlanPayload


class TestBindPort:
    def test_with_no_trunk(self, mocker, port_context, understack_driver):
        mocker.patch("neutron_understack.utils.fetch_connected_interface_uuid")

        understack_driver.bind_port(port_context)

        utils.fetch_connected_interface_uuid.assert_called_once()
        understack_driver.undersync.sync_devices.assert_called_once()

    @pytest.mark.parametrize("port_dict", [{"trunk": True}], indirect=True)
    def test_with_trunk_details(self, mocker, understack_driver, port_context, port_id):
        mocker.patch(
            "neutron_understack.utils.fetch_subport_network_id", return_value="112233"
        )

        understack_driver.bind_port(port_context)


class Test_DeleteTenantPortOnUnbound:
    @pytest.mark.parametrize("port_dict", [{"trunk": True}], indirect=True)
    def test_when_trunk_details_are_present(
        self, mocker, understack_driver, port_context, vlan_group_id, port_id
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_subport_network_id", return_value="112233"
        )

        mocker.patch.object(
            understack_driver.nb,
            "detach_port",
            return_value=str(vlan_group_id),
        )
        port_context._binding.vif_type = portbindings.VIF_TYPE_UNBOUND

        understack_driver._delete_tenant_port_on_unbound(port_context)


class TestCreateSubnetPostCommit:
    def test_create_private(self, understack_driver, subnet_context, subnet):
        understack_driver.create_subnet_postcommit(subnet_context)

        understack_driver.nb.subnet_create.assert_called_once_with(
            subnet_uuid=subnet.id,
            prefix=subnet.cidr,
            namespace_name=subnet.network_id,
            tenant_uuid=ANY,
        )

    @pytest.mark.parametrize("subnet", [{"external": True}], indirect=True)
    def test_create_public(self, understack_driver, subnet_context, subnet):
        understack_driver.create_subnet_postcommit(subnet_context)

        understack_driver.nb.subnet_create.assert_called_once_with(
            subnet_uuid=subnet.id,
            prefix=subnet.cidr,
            namespace_name="Global",
            tenant_uuid=ANY,
        )
        understack_driver.nb.associate_subnet_with_network.assert_called_once_with(
            role="svi_vxlan_anycast_gateway",
            network_uuid=subnet.network_id,
            subnet_uuid=subnet.id,
        )


class TestDeleteSubnetPostCommit:
    @pytest.mark.parametrize("subnet", [{"external": True}], indirect=True)
    def test_delete_public(self, understack_driver, subnet_context):
        understack_driver.delete_subnet_postcommit(subnet_context)

        understack_driver.nb.subnet_delete.assert_called_once()


class TestNetworkSegmentEventCallbacks:
    @pytest.mark.parametrize(
        "vlan_network_segment", [{"physical_network": "f20-2-network"}], indirect=True
    )
    def test__create_vlan_valid_segment(
        self, mocker, vlan_network_segment, understack_driver
    ):
        mocker.patch(
            "neutron_understack.utils.is_valid_vlan_network_segment", return_value=True
        )

        mock_create = mocker.patch.object(
            understack_driver.nb, "create_vlan_and_associate_vlan_to_ucvni"
        )

        understack_driver._create_vlan(vlan_network_segment)

        mock_create.assert_called_once()
        vlan_payload: VlanPayload = mock_create.call_args[0][0]

        assert vlan_payload.vid == 1800
        assert vlan_payload.vlan_group_name == "f20-2-network"

    def test__create_vlan_invalid_segment(
        self, mocker, vlan_network_segment, understack_driver
    ):
        mocker.patch(
            "neutron_understack.utils.is_valid_vlan_network_segment", return_value=False
        )
        mock_create = mocker.patch.object(
            understack_driver.nb, "create_vlan_and_associate_vlan_to_ucvni"
        )

        understack_driver._create_vlan(vlan_network_segment)

        mock_create.assert_not_called()

    @pytest.mark.parametrize(
        "vlan_network_segment",
        [{"physical_network": "f20-2-network", "segmentation_id": 100}],
        indirect=True,
    )
    def test__delete_vlan(self, mocker, vlan_network_segment, understack_driver):
        mock_delete = mocker.patch.object(understack_driver.nb, "delete_vlan")
        understack_driver._delete_vlan(vlan_network_segment)
        mock_delete.assert_called_once_with(vlan_id=vlan_network_segment.get("id"))


class TestCreateNetworkPostCommit:
    @pytest.mark.usefixtures("ml2_understack_conf")
    def test_vxlan_network(
        self,
        mocker,
        understack_driver,
        network_context,
        network_id,
        ucvni_group_id,
        project_id,
    ):
        mocker.patch.object(understack_driver, "_create_nautobot_namespace")
        understack_driver.create_network_postcommit(network_context)
        understack_driver.nb.ucvni_create.assert_called_once_with(
            network_id=str(network_id),
            project_id=str(project_id),
            ucvni_group=str(ucvni_group_id),
            segmentation_id=network_context.current["provider:segmentation_id"],
            network_name=network_context.current["name"],
        )
        understack_driver._create_nautobot_namespace.assert_called_once_with(
            str(network_id),
            network_context.current["router:external"],
        )
