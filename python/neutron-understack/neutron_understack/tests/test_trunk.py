import pytest
from neutron.plugins.ml2.driver_context import portbindings
from oslo_config import cfg

from neutron_understack.trunk import SubportSegmentationIDError


class TestSubportsAdded:
    def test_that_handler_is_called(
        self, mocker, understack_trunk_driver, trunk_payload, subport, trunk
    ):
        mocker.patch.object(
            understack_trunk_driver, "_handle_tenant_vlan_id_and_switchport_config"
        )

        understack_trunk_driver.subports_added("", "", "", trunk_payload)

        (
            understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config.assert_called_once_with(
                [subport], trunk
            )
        )


class TestTrunkCreated:
    def test_when_subports_are_present(
        self, mocker, understack_trunk_driver, trunk_payload, subport, trunk
    ):
        mocker.patch.object(
            understack_trunk_driver, "_handle_tenant_vlan_id_and_switchport_config"
        )
        understack_trunk_driver.trunk_created("", "", "", trunk_payload)

        (
            understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config.assert_called_once_with(
                [subport], trunk
            )
        )

    def test_when_subports_are_not_present(
        self, mocker, understack_trunk_driver, trunk_payload, subport, trunk
    ):
        mocker.patch.object(
            understack_trunk_driver, "_handle_tenant_vlan_id_and_switchport_config"
        )
        trunk.sub_ports = []
        understack_trunk_driver.trunk_created("", "", "", trunk_payload)

        (
            understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config.assert_not_called()
        )


@pytest.mark.usefixtures("utils_fetch_subport_network_id_patch")
class Test_HandleTenantVlanIDAndSwitchportConfig:
    def test_when_ucvni_tenant_vlan_id_is_not_set_yet(
        self, mocker, understack_trunk_driver, trunk, subport, network_id, vlan_num
    ):
        mocker.patch.object(
            understack_trunk_driver.nb, "fetch_ucvni_tenant_vlan_id", return_value=None
        )
        mocker.patch.object(
            understack_trunk_driver, "_handle_parent_port_switchport_config"
        )
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )

        understack_trunk_driver.nb.add_tenant_vlan_tag_to_ucvni.assert_called_once_with(
            network_uuid=str(network_id), vlan_tag=vlan_num
        )
        understack_trunk_driver._handle_parent_port_switchport_config.assert_called_once()

    def test_when_segmentation_id_is_different_to_tenant_vlan_id(
        self, mocker, understack_trunk_driver, vlan_num, subport, trunk
    ):
        mocker.patch.object(
            understack_trunk_driver.nb,
            "fetch_ucvni_tenant_vlan_id",
            return_value=(vlan_num + 1),
        )
        mocker.patch.object(
            understack_trunk_driver, "_handle_parent_port_switchport_config"
        )
        mocker.patch.object(subport, "delete")

        with pytest.raises(SubportSegmentationIDError):
            understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
                [subport], trunk
            )

    def test_when_parent_port_is_bound(
        self,
        mocker,
        understack_trunk_driver,
        trunk,
        subport,
        port_object,
        vlan_group_id,
        port_id,
        network_id,
    ):
        mocker.patch.object(understack_trunk_driver, "_handle_tenant_vlan_id_config")
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch.object(
            understack_trunk_driver.nb,
            "prep_switch_interface",
            return_value={"vlan_group_id": vlan_group_id},
        )
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )

        understack_trunk_driver.nb.prep_switch_interface.assert_called_once_with(
            connected_interface_id=str(port_id),
            ucvni_uuid=str(network_id),
            vlan_tag=None,
            modify_native_vlan=False,
        )
        understack_trunk_driver.undersync.sync_devices.assert_called_once_with(
            vlan_group_uuids=str(vlan_group_id),
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def test_when_parent_port_is_unbound(
        self, mocker, understack_trunk_driver, trunk, subport, port_object
    ):
        mocker.patch.object(understack_trunk_driver, "_handle_tenant_vlan_id_config")
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch.object(
            understack_trunk_driver, "_add_subport_network_to_parent_port_switchport"
        )
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )

        (
            understack_trunk_driver._add_subport_network_to_parent_port_switchport.assert_not_called()
        )


class TestSubportsDeleted:
    def test_that_clean_parent_port_is_triggered(
        self, mocker, understack_trunk_driver, trunk_payload, trunk, subport
    ):
        mocker.patch.object(
            understack_trunk_driver, "_clean_parent_port_switchport_config"
        )

        understack_trunk_driver.subports_deleted("", "", "", trunk_payload)

        (
            understack_trunk_driver._clean_parent_port_switchport_config.assert_called_once_with(
                trunk, [subport]
            )
        )


class TestTrunkDeleted:
    def test_when_subports_are_present(
        self, mocker, understack_trunk_driver, trunk_payload, trunk, subport
    ):
        mocker.patch.object(
            understack_trunk_driver, "_clean_parent_port_switchport_config"
        )

        understack_trunk_driver.trunk_deleted("", "", "", trunk_payload)

        (
            understack_trunk_driver._clean_parent_port_switchport_config.assert_called_once_with(
                trunk, [subport]
            )
        )

    def test_when_subports_are_not_present(
        self, mocker, understack_trunk_driver, trunk_payload, trunk, subport
    ):
        mocker.patch.object(
            understack_trunk_driver, "_clean_parent_port_switchport_config"
        )

        trunk.sub_ports = []
        understack_trunk_driver.trunk_deleted("", "", "", trunk_payload)

        (
            understack_trunk_driver._clean_parent_port_switchport_config.assert_not_called()
        )


@pytest.mark.usefixtures("utils_fetch_subport_network_id_patch")
class Test_CleanParentPortSwitchportConfig:
    def test_when_parent_port_is_bound(
        self,
        mocker,
        understack_trunk_driver,
        trunk,
        subport,
        port_object,
        vlan_group_id,
        port_id,
        network_id,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch.object(
            understack_trunk_driver.nb, "detach_port", return_value=str(vlan_group_id)
        )

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        understack_trunk_driver.nb.detach_port.assert_called_once_with(
            connected_interface_id=str(port_id), ucvni_uuid=str(network_id)
        )
        understack_trunk_driver.undersync.sync_devices.assert_called_once_with(
            vlan_group_uuids=str(vlan_group_id),
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def test_when_parent_port_is_unbound(
        self, mocker, understack_trunk_driver, port_object, trunk, subport
    ):
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch.object(
            understack_trunk_driver,
            "_remove_subport_network_from_parent_port_switchport",
        )

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        (
            understack_trunk_driver._remove_subport_network_from_parent_port_switchport.assert_not_called()
        )
