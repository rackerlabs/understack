import pytest
from neutron.plugins.ml2.driver_context import portbindings
from neutron_lib import exceptions as exc

from neutron_understack import utils
from neutron_understack.trunk import SubportSegmentationIDError
from neutron_understack.trunk import SubportSegmentationIDRangeError


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


@pytest.mark.usefixtures("_utils_fetch_subport_network_id_patch")
class Test_HandleTenantVlanIDAndSwitchportConfig:
    def test_that_check_subports_segmentation_id_is_called(
        self, mocker, understack_trunk_driver, trunk, subport
    ):
        parent_port = mocker.patch("neutron_understack.utils.fetch_port_object")
        mocker.patch(
            "neutron_understack.utils.parent_port_is_bound", return_value=False
        )
        subport_seg_id_check = mocker.patch.object(
            understack_trunk_driver, "_check_subports_segmentation_id"
        )
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )

        subport_seg_id_check.assert_called_once_with(
            [subport], trunk.id, parent_port.return_value
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
        mocker.patch.object(understack_trunk_driver, "_check_subports_segmentation_id")
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch(
            "neutron_understack.utils.allocate_dynamic_segment",
            return_value=vlan_network_segment,
        )
        mocker.patch(
            "neutron_understack.utils.network_segment_by_physnet", return_value=None
        )
        mocker.patch("neutron_understack.utils.create_binding_profile_level")
        add_subports_networks = mocker.patch.object(
            understack_trunk_driver, "_add_subports_networks_to_parent_port_switchport"
        )
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )
        add_subports_networks.assert_called_once()

    def test_when_parent_port_is_unbound(
        self, mocker, understack_trunk_driver, trunk, subport, port_object
    ):
        mocker.patch.object(understack_trunk_driver, "_check_subports_segmentation_id")
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        add_subports_networks = mocker.patch.object(
            understack_trunk_driver, "_add_subports_networks_to_parent_port_switchport"
        )
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )
        add_subports_networks.assert_not_called()


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


@pytest.mark.usefixtures("_utils_fetch_subport_network_id_patch")
class Test_CleanParentPortSwitchportConfig:
    def test_when_parent_port_is_bound(
        self,
        mocker,
        understack_trunk_driver,
        trunk,
        subport,
        port_object,
        host_id,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        deallocate = mocker.patch.object(
            understack_trunk_driver, "_handle_segment_deallocation"
        )

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        deallocate.assert_called_once_with([subport], str(host_id))

    def test_when_parent_port_is_unbound(
        self, mocker, understack_trunk_driver, port_object, trunk, subport
    ):
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        deallocate = mocker.patch.object(
            understack_trunk_driver, "_handle_segment_deallocation"
        )

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        deallocate.assert_not_called()


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
        mocker.patch(
            "neutron_understack.utils.is_dynamic_network_segment", return_value=True
        )
        mocker.patch("neutron_understack.utils.release_dynamic_segment")

        understack_trunk_driver._handle_segment_deallocation([subport], str(host_id))

        utils.release_dynamic_segment.assert_called_once_with(str(network_segment_id))
        port_binding_level.delete.assert_called_once()

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
        mocker.patch("neutron_understack.utils.release_dynamic_segment")

        understack_trunk_driver._handle_segment_deallocation([subport], str(host_id))

        utils.release_dynamic_segment.assert_not_called()
        port_binding_level.delete.assert_called_once()


class TestConfigureTrunk:
    def test_returns_without_configuring_when_port_is_not_a_trunk_parent(
        self,
        mocker,
        understack_trunk_driver,
        port_id,
        vlan_network_segment,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_trunk_by_parent_port", return_value=None
        )
        add_subports = mocker.patch.object(
            understack_trunk_driver, "_add_subports_networks_to_parent_port_switchport"
        )

        understack_trunk_driver.configure_trunk(port_id, vlan_network_segment)

        add_subports.assert_not_called()

    def test_that_add_subports_networks_is_called(
        self,
        mocker,
        understack_trunk_driver,
        trunk,
        port_object,
        port_id,
        vlan_network_segment,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_trunk_by_parent_port", return_value=trunk
        )
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=str(trunk.id),
        )
        add_subports = mocker.patch.object(
            understack_trunk_driver, "_add_subports_networks_to_parent_port_switchport"
        )

        understack_trunk_driver.configure_trunk(port_id, vlan_network_segment)

        add_subports.assert_called_once_with(
            parent_port=port_object,
            subports=trunk.sub_ports,
        )

    def test_rejects_subport_matching_newly_selected_native_vlan(
        self,
        mocker,
        understack_trunk_driver,
        port_object,
        port_id,
        trunk_id,
        subport,
        vlan_network_segment,
        trunk,
    ):
        trunk.id = trunk_id
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch(
            "neutron_understack.utils.fetch_trunk_by_parent_port", return_value=trunk
        )
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        add_subports = mocker.patch.object(
            understack_trunk_driver, "_add_subports_networks_to_parent_port_switchport"
        )
        subport.segmentation_id = vlan_network_segment.segmentation_id

        with pytest.raises(SubportSegmentationIDError, match="matches the native VLAN"):
            understack_trunk_driver.configure_trunk(port_id, vlan_network_segment)

        add_subports.assert_not_called()

    def test_network_node_trunk_allows_native_vlan_as_subport_tag(
        self,
        mocker,
        understack_trunk_driver,
        port_object,
        port_id,
        trunk_id,
        subport,
        vlan_network_segment,
        trunk,
    ):
        trunk.id = trunk_id
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch(
            "neutron_understack.utils.fetch_trunk_by_parent_port", return_value=trunk
        )
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=str(trunk_id),
        )
        add_subports = mocker.patch.object(
            understack_trunk_driver, "_add_subports_networks_to_parent_port_switchport"
        )
        subport.segmentation_id = vlan_network_segment.segmentation_id

        understack_trunk_driver.configure_trunk(port_id, vlan_network_segment)

        add_subports.assert_called_once_with(
            parent_port=port_object,
            subports=[subport],
        )


class TestCleanTrunk:
    def test_that_segments_are_deallocated(
        self, mocker, understack_trunk_driver, subport
    ):
        deallocate = mocker.patch.object(
            understack_trunk_driver, "_handle_segment_deallocation"
        )

        understack_trunk_driver.clean_trunk({"sub_ports": [subport]}, "host-a")

        deallocate.assert_called_once_with([subport], "host-a")

    def test_without_subports(self, mocker, understack_trunk_driver):
        deallocate = mocker.patch.object(
            understack_trunk_driver, "_handle_segment_deallocation"
        )

        understack_trunk_driver.clean_trunk({}, "host-a")

        deallocate.assert_called_once_with([], "host-a")


@pytest.mark.usefixtures("oslo_config")
class TestCheckSubportsSegmentationId:
    def test_when_trunk_id_is_network_node_trunk_id(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
        subport,
        port_object,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=str(trunk_id),
        )
        find_segment = mocker.patch(
            "neutron_understack.utils.network_segment_by_physnet"
        )
        subport.segmentation_id = 4000

        result = understack_trunk_driver._check_subports_segmentation_id(
            [subport], str(trunk_id), port_object
        )

        find_segment.assert_not_called()
        assert result is None

    def test_when_segmentation_id_differs_from_native_vlan(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
        subport,
        port_object,
        network_id,
        vlan_network_segment,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        find_segment = mocker.patch(
            "neutron_understack.utils.network_segment_by_physnet",
            return_value=vlan_network_segment,
        )
        port_object.network_id = str(network_id)
        subport.segmentation_id = 2000

        result = understack_trunk_driver._check_subports_segmentation_id(
            [subport], trunk_id, port_object
        )

        find_segment.assert_called_once_with(
            network_id=str(network_id), physnet="physnet"
        )
        assert result is None

    @pytest.mark.parametrize("segmentation_id", [2, 3871])
    def test_when_segmentation_id_is_on_configured_range_boundary(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
        subport,
        port_object,
        segmentation_id,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        subport.segmentation_id = segmentation_id

        result = understack_trunk_driver._check_subports_segmentation_id(
            [subport], trunk_id, port_object
        )

        assert result is None

    @pytest.mark.parametrize("segmentation_id", [1, 3872, 4094])
    def test_when_segmentation_id_is_outside_configured_range(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
        subport,
        port_object,
        segmentation_id,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        find_segment = mocker.patch(
            "neutron_understack.utils.network_segment_by_physnet"
        )
        subport.segmentation_id = segmentation_id

        with pytest.raises(
            SubportSegmentationIDRangeError, match="outside the configured"
        ):
            understack_trunk_driver._check_subports_segmentation_id(
                [subport], trunk_id, port_object
            )

        find_segment.assert_not_called()

    def test_uses_configured_tenant_vlan_range(
        self,
        mocker,
        oslo_config,
        understack_trunk_driver,
        trunk_id,
        subport,
        port_object,
    ):
        oslo_config.config(
            default_tenant_vlan_id_range=[100, 200], group="ml2_understack"
        )
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        subport.segmentation_id = 99

        with pytest.raises(SubportSegmentationIDRangeError, match="100-200"):
            understack_trunk_driver._check_subports_segmentation_id(
                [subport], trunk_id, port_object
            )

    def test_when_segmentation_id_matches_native_vlan(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
        subport,
        port_object,
        network_id,
        vlan_network_segment,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        mocker.patch(
            "neutron_understack.utils.network_segment_by_physnet",
            return_value=vlan_network_segment,
        )
        port_object.network_id = str(network_id)
        subport.segmentation_id = vlan_network_segment.segmentation_id

        with pytest.raises(SubportSegmentationIDError, match="matches the native VLAN"):
            understack_trunk_driver._check_subports_segmentation_id(
                [subport], trunk_id, port_object
            )

    def test_when_parent_port_is_unbound(
        self, mocker, understack_trunk_driver, trunk_id, subport, port_object
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        subport.segmentation_id = 2000
        find_segment = mocker.patch(
            "neutron_understack.utils.network_segment_by_physnet"
        )

        result = understack_trunk_driver._check_subports_segmentation_id(
            [subport], trunk_id, port_object
        )

        find_segment.assert_not_called()
        assert result is None


@pytest.mark.parametrize("binding_profile", [{"physical_network": None}], indirect=True)
class TestMissingPhysicalNetwork:
    """physical_network is mandatory for allocating a subport's segment.

    This driver needs it to know which VLAN segment range the segment comes
    from, so subport creation is rejected without it. Teardown does not need it
    -- deciding whether Undersync can be notified is the undersync driver's
    problem, not this one's.
    """

    def test_precommit_create_rejects_the_request(
        self, understack_trunk_driver, port_object, subport
    ):
        with pytest.raises(exc.BadRequest, match="physical_network is required"):
            understack_trunk_driver._add_subports_networks_to_parent_port_switchport(
                port_object, [subport]
            )

    def test_teardown_still_releases_segments(
        self, mocker, understack_trunk_driver, trunk, subport, port_object, host_id
    ):
        """A missing physnet must not leak the subports' VLANs."""
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        deallocate = mocker.patch.object(
            understack_trunk_driver, "_handle_segment_deallocation"
        )

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        deallocate.assert_called_once_with([subport], str(host_id))
