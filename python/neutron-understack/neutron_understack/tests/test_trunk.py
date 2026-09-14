import logging

import pytest
from neutron.plugins.ml2.driver_context import portbindings
from neutron_lib import exceptions as exc

from neutron_understack import trunk as trunk_module
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


@pytest.mark.usefixtures("_utils_fetch_subport_network_id_patch")
class Test_HandleTenantVlanIDAndSwitchportConfig:
    def test_that_check_subports_segmentation_id_is_called(
        self, mocker, understack_trunk_driver, trunk, subport, network_id, vlan_num
    ):
        mocker.patch("neutron_understack.utils.fetch_port_object")
        mocker.patch(
            "neutron_understack.utils.parent_port_is_bound", return_value=False
        )
        subport_seg_id_check = mocker.patch.object(
            understack_trunk_driver, "_check_subports_segmentation_id"
        )
        understack_trunk_driver._handle_tenant_vlan_id_and_switchport_config(
            [subport], trunk
        )

        subport_seg_id_check.assert_called_once()

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

    def test_subports_add_post(
        self,
        mocker,
        trunk,
        port_object,
        understack_trunk_driver,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch("neutron_understack.utils.parent_port_is_bound", return_value=True)
        understack_trunk_driver.subports_added_post(
            None, None, None, mocker.Mock(states=[trunk])
        )

        understack_trunk_driver.undersync.sync.assert_called_once_with("physnet")

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

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        understack_trunk_driver.undersync.sync.assert_called_once_with("physnet")

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


class TestCheckSubportsSegmentationId:
    def test_when_trunk_id_is_network_node_trunk_id(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
    ):
        # Mock fetch_network_node_trunk_id to return the trunk_id
        mocker.patch(
            "neutron_understack.trunk.fetch_network_node_trunk_id",
            return_value=str(trunk_id),
        )
        # Mock to ensure the function returns early and doesn't call this
        allowed_ranges_mock = mocker.patch(
            "neutron_understack.utils.allowed_tenant_vlan_id_ranges"
        )
        result = understack_trunk_driver._check_subports_segmentation_id(
            [], str(trunk_id)
        )
        # Should not call allowed_tenant_vlan_id_ranges because it returns early
        allowed_ranges_mock.assert_not_called()
        assert result is None

    def test_when_segmentation_id_is_in_allowed_range(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
        subport,
    ):
        # Mock fetch_network_node_trunk_id to return a different trunk ID
        mocker.patch(
            "neutron_understack.trunk.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        allowed_ranges = mocker.patch(
            "neutron_understack.utils.allowed_tenant_vlan_id_ranges",
            return_value=[(1, 1500)],
        )
        subport.segmentation_id = 500
        result = understack_trunk_driver._check_subports_segmentation_id(
            [subport], trunk_id
        )
        allowed_ranges.assert_called_once()
        assert result is None

    def test_when_segmentation_id_is_not_in_allowed_range(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
        subport,
    ):
        # Mock fetch_network_node_trunk_id to return a different trunk ID
        mocker.patch(
            "neutron_understack.trunk.fetch_network_node_trunk_id",
            return_value="different-trunk-id",
        )
        mocker.patch(
            "neutron_understack.utils.allowed_tenant_vlan_id_ranges",
            return_value=[(1, 1500)],
        )
        subport.segmentation_id = 1600
        with pytest.raises(SubportSegmentationIDError):
            understack_trunk_driver._check_subports_segmentation_id([subport], trunk_id)


@pytest.mark.parametrize("binding_profile", [{"physical_network": None}], indirect=True)
class TestMissingPhysicalNetwork:
    """physical_network is mandatory: there is no fallback lookup.

    It is enforced on the precommit hooks, where raising aborts the
    transaction. The postcommit hooks cannot roll anything back, so they log
    and degrade instead of raising.
    """

    @pytest.fixture
    def _bound_parent_port(self, mocker, port_object) -> None:
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch("neutron_understack.utils.parent_port_is_bound", return_value=True)

    def test_precommit_create_rejects_the_request(
        self, understack_trunk_driver, port_object, subport
    ):
        with pytest.raises(exc.BadRequest, match="physical_network is required"):
            understack_trunk_driver._add_subports_networks_to_parent_port_switchport(
                port_object, [subport]
            )

    @pytest.mark.usefixtures("_bound_parent_port")
    def test_subports_deleted_precommit_rejects_the_request(
        self, mocker, understack_trunk_driver, trunk
    ):
        with pytest.raises(exc.BadRequest, match="physical_network is required"):
            understack_trunk_driver.subports_deleted_precommit(
                None, None, None, mocker.Mock(states=[trunk])
            )

    @pytest.mark.usefixtures("_bound_parent_port")
    def test_trunk_deleted_precommit_rejects_the_request(
        self, mocker, understack_trunk_driver, trunk
    ):
        with pytest.raises(exc.BadRequest, match="physical_network is required"):
            understack_trunk_driver.trunk_deleted_precommit(
                None, None, None, mocker.Mock(states=[trunk])
            )

    def test_precommit_delete_ignores_unbound_parent_port(
        self, mocker, understack_trunk_driver, trunk, port_object
    ):
        """An unbound parent port has no switchport config to tear down.

        There is nothing to validate, so a missing physnet must not block the
        delete.
        """
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch(
            "neutron_understack.utils.parent_port_is_bound", return_value=False
        )

        understack_trunk_driver.subports_deleted_precommit(
            None, None, None, mocker.Mock(states=[trunk])
        )

    @pytest.mark.usefixtures("_bound_parent_port")
    def test_subports_added_post_logs_instead_of_raising(
        self, mocker, caplog, understack_trunk_driver, trunk
    ):
        caplog.set_level(logging.ERROR, logger=trunk_module.LOG.name)

        understack_trunk_driver.subports_added_post(
            None, None, None, mocker.Mock(states=[trunk])
        )

        assert "physical_network is required" in caplog.text
        understack_trunk_driver.undersync.sync.assert_not_called()

    @pytest.mark.usefixtures(
        "_bound_parent_port", "_utils_fetch_subport_network_id_patch"
    )
    def test_clean_parent_port_releases_segments_without_syncing(
        self, mocker, caplog, understack_trunk_driver, trunk, subport
    ):
        """Teardown still runs postcommit so the subports' VLANs do not leak.

        Only the undersync call is skipped, since there is no vlan group to
        reconcile.
        """
        deallocate = mocker.patch.object(
            understack_trunk_driver, "_handle_segment_deallocation"
        )
        caplog.set_level(logging.ERROR, logger=trunk_module.LOG.name)

        understack_trunk_driver._clean_parent_port_switchport_config(trunk, [subport])

        assert "physical_network is required" in caplog.text
        deallocate.assert_called_once()
        understack_trunk_driver.undersync.sync.assert_not_called()
