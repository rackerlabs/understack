import pytest
from neutron_lib.api.definitions import portbindings


class TestFetchConnectedInterfaceUUID:
    def test_with_normal_uuid(self, port_context, understack_driver, port_id):
        result = understack_driver.fetch_connected_interface_uuid(port_context.current)
        assert result == str(port_id)

    @pytest.mark.parametrize("binding_profile", [{"port_id": 11}], indirect=True)
    def test_with_integer(self, port_context, understack_driver):
        with pytest.raises(ValueError):
            understack_driver.fetch_connected_interface_uuid(port_context.current)


class TestUpdateNautobot:
    def test_for_tenant_network(self, mocker, understack_driver, vlan_group_id):
        attrs = {"vlan_group_id": str(vlan_group_id)}
        mocker.patch.object(
            understack_driver.nb, "prep_switch_interface", return_value=attrs
        )
        understack_driver.update_nautobot("111", "222", 333)

        understack_driver.nb.prep_switch_interface.assert_called_once_with(
            connected_interface_id="222", ucvni_uuid="111", vlan_tag=333
        )

    def test_for_provisioning_network(self, mocker, understack_driver, vlan_group_id):
        mocker.patch.object(
            understack_driver.nb,
            "configure_port_status",
            return_value={"device": {"id": "444"}},
        )
        mocker.patch.object(
            understack_driver.nb,
            "fetch_vlan_group_uuid",
            return_value=str(vlan_group_id),
        )

        understack_driver.update_nautobot("change_me", "333", 123)

        understack_driver.nb.configure_port_status.assert_called_once_with(
            "333", "Provisioning-Interface"
        )
        understack_driver.nb.fetch_vlan_group_uuid.assert_called_once_with("444")


class TestUpdatePortPostcommit:
    @pytest.mark.parametrize(
        "port_dict", [{"vif_type": portbindings.VIF_TYPE_UNBOUND}], indirect=True
    )
    def test_vif_type_unbound(self, mocker, understack_driver, port_context):
        spy_delete_tenant_port = mocker.spy(
            understack_driver, "_delete_tenant_port_on_unbound"
        )
        result = understack_driver.update_port_postcommit(port_context)

        spy_delete_tenant_port.assert_called_once()
        assert result is None


@pytest.mark.usefixtures("update_nautobot_patch")
class TestBindPort:
    def test_with_no_trunk(self, mocker, port_context, understack_driver):
        mocker.patch.object(understack_driver, "_configure_trunk")
        mocker.patch.object(understack_driver, "fetch_connected_interface_uuid")

        understack_driver.bind_port(port_context)

        understack_driver.update_nautobot.assert_called_once()
        understack_driver._configure_trunk.assert_not_called()
        understack_driver.fetch_connected_interface_uuid.assert_called_once()
        understack_driver.undersync.sync_devices.assert_called_once()

    @pytest.mark.parametrize("port_dict", [{"trunk": True}], indirect=True)
    def test_with_trunk_details(self, mocker, understack_driver, port_context, port_id):
        mocker.patch(
            "neutron_understack.utils.fetch_subport_network_id", return_value="112233"
        )

        understack_driver.bind_port(port_context)
        understack_driver.nb.prep_switch_interface.assert_called_once_with(
            connected_interface_id=str(port_id),
            ucvni_uuid="112233",
            modify_native_vlan=False,
            vlan_tag=None,
        )


class Test_DeleteTenantPortOnUnbound:
    @pytest.mark.parametrize("port_dict", [{"trunk": True}], indirect=True)
    def test_when_trunk_details_are_present(
        self, mocker, understack_driver, port_context, port_id
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_subport_network_id", return_value="112233"
        )

        mocker.patch.object(
            understack_driver.nb,
            "detach_port",
            return_value=str(port_id),
        )
        port_context._binding.vif_type = portbindings.VIF_TYPE_UNBOUND

        understack_driver._delete_tenant_port_on_unbound(port_context)
        understack_driver.nb.detach_port.assert_any_call(str(port_id), "112233")


class TestCreateSubnetPostCommit:
    def test_create_private(self, understack_driver, subnet_context, subnet):
        understack_driver.create_subnet_postcommit(subnet_context)

        understack_driver.nb.subnet_create.assert_called_once_with(
            subnet_uuid=subnet.id,
            prefix=subnet.cidr,
            namespace_name=subnet.network_id,
        )

    @pytest.mark.parametrize("subnet", [{"external": True}], indirect=True)
    def test_create_public(self, understack_driver, subnet_context, subnet):
        understack_driver.create_subnet_postcommit(subnet_context)

        understack_driver.nb.subnet_create.assert_called_once_with(
            subnet_uuid=subnet.id,
            prefix=subnet.cidr,
            namespace_name="Global",
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
