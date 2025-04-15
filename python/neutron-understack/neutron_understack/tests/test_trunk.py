import pytest
from neutron.plugins.ml2.driver_context import portbindings
from oslo_config import cfg

from neutron_understack import utils
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

        mocker.patch("neutron_understack.utils.fetch_port_object")
        mocker.patch(
            "neutron_understack.utils.parent_port_is_bound", return_value=False
        )

        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )

        understack_trunk_driver.nb.add_tenant_vlan_tag_to_ucvni.assert_called_once_with(
            network_uuid=str(network_id), vlan_tag=vlan_num
        )

    def test_when_segmentation_id_is_different_to_tenant_vlan_id(
        self, mocker, understack_trunk_driver, vlan_num, subport, trunk
    ):
        mocker.patch.object(
            understack_trunk_driver.nb,
            "fetch_ucvni_tenant_vlan_id",
            return_value=(vlan_num + 1),
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
        port_id,
        vlan_network_segment,
    ):
        mocker.patch.object(understack_trunk_driver, "_handle_tenant_vlan_id_config")
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch(
            "neutron_understack.utils.allocate_dynamic_segment",
            return_value=vlan_network_segment,
        )
        mocker.patch("neutron_understack.utils.create_binding_profile_level")
        mocker.patch.object(understack_trunk_driver.nb, "add_port_vlan_associations")
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )

        understack_trunk_driver.nb.add_port_vlan_associations.assert_called_once_with(
            interface_uuid=str(port_id),
            vlan_group_name="a1-1-network",
            allowed_vlans_ids={1800},
        )
        understack_trunk_driver.undersync.sync_devices.assert_called_once_with(
            vlan_group="a1-1-network",
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
            understack_trunk_driver, "_add_subports_networks_to_parent_port_switchport"
        )
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )

        (
            understack_trunk_driver._add_subports_networks_to_parent_port_switchport.assert_not_called()
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
        port_id,
        network_id,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch.object(
            understack_trunk_driver,
            "_handle_segment_deallocation",
            return_value={network_id},
        )
        mocker.patch.object(
            understack_trunk_driver.nb, "remove_port_network_associations"
        )

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        understack_trunk_driver.nb.remove_port_network_associations.assert_called_once_with(
            interface_uuid=str(port_id), network_ids_to_remove={network_id}
        )
        understack_trunk_driver.undersync.sync_devices.assert_called_once_with(
            vlan_group="a1-1-network",
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def test_when_parent_port_is_unbound(
        self, mocker, understack_trunk_driver, port_object, trunk, subport
    ):
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch.object(understack_trunk_driver, "_handle_subports_removal")

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        understack_trunk_driver._handle_subports_removal.assert_not_called()


class Test_HandleSegmentDeallocation:
    def test_when_segment_is_unused_by_other_ports(
        self,
        mocker,
        understack_trunk_driver,
        subport,
        host_id,
        network_segment_id,
        port_binding_level,
        vlan_network_segment,
    ):
        mocker.patch.object(port_binding_level, "delete")
        mocker.patch(
            "neutron_understack.utils.port_binding_level_by_port_id",
            return_value=port_binding_level,
        )
        mocker.patch(
            "neutron_understack.utils.network_segment_by_id",
            return_value=vlan_network_segment,
        )
        mocker.patch(
            "neutron_understack.utils.ports_bound_to_segment", return_value=False
        )
        mocker.patch.object(understack_trunk_driver.nb, "delete_vlan")
        mocker.patch("neutron_understack.utils.release_dynamic_segment")

        result = understack_trunk_driver._handle_segment_deallocation(
            [subport], str(host_id)
        )

        utils.release_dynamic_segment.assert_called_once_with(str(network_segment_id))
        understack_trunk_driver.nb.delete_vlan.assert_called_once_with(
            vlan_id=str(network_segment_id)
        )
        port_binding_level.delete.assert_called_once()
        assert result == {str(network_segment_id)}

    def test_when_segment_is_used_by_other_ports(
        self,
        mocker,
        understack_trunk_driver,
        subport,
        host_id,
        network_segment_id,
        port_binding_level,
        vlan_network_segment,
    ):
        mocker.patch.object(port_binding_level, "delete")
        mocker.patch(
            "neutron_understack.utils.port_binding_level_by_port_id",
            return_value=port_binding_level,
        )
        mocker.patch(
            "neutron_understack.utils.network_segment_by_id",
            return_value=vlan_network_segment,
        )
        mocker.patch(
            "neutron_understack.utils.ports_bound_to_segment", return_value=True
        )
        mocker.patch.object(understack_trunk_driver.nb, "delete_vlan")
        mocker.patch("neutron_understack.utils.release_dynamic_segment")

        result = understack_trunk_driver._handle_segment_deallocation(
            [subport], str(host_id)
        )

        utils.release_dynamic_segment.assert_not_called()
        understack_trunk_driver.nb.delete_vlan.assert_not_called()
        port_binding_level.delete.assert_called_once()
        assert result == {str(network_segment_id)}


class TestConfigureTrunk:
    def test_that_add_subports_networks_is_called(
        self,
        mocker,
        understack_trunk_driver,
        port_object,
        port_id,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch.object(
            understack_trunk_driver, "_add_subports_networks_to_parent_port_switchport"
        )
        understack_trunk_driver.configure_trunk({}, port_id)

        understack_trunk_driver._add_subports_networks_to_parent_port_switchport.assert_called_once_with(
            parent_port=port_object,
            subports=[],
            invoke_undersync=False,
        )


class TestCleanTrunk:
    def test_that_handle_subports_removal_is_called(
        self,
        mocker,
        understack_trunk_driver,
    ):
        mocker.patch.object(understack_trunk_driver, "_handle_subports_removal")

        understack_trunk_driver.clean_trunk({}, {}, "")

        understack_trunk_driver._handle_subports_removal.assert_called_once_with(
            binding_profile={},
            binding_host="",
            subports=[],
            invoke_undersync=False,
        )
