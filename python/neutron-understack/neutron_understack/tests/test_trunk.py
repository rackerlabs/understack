import contextlib

import pytest
from neutron.plugins.ml2.driver_context import portbindings
from neutron_lib import constants as p_const
from neutron_lib import exceptions as exc
from neutron_lib.services.trunk import constants as trunk_consts

from neutron_understack import utils
from neutron_understack.trunk import SubportSegmentationIDError
from neutron_understack.trunk import claim_subports
from neutron_understack.trunk import update_trunk_state


@pytest.fixture
def trunk_status(mocker, trunk):
    """Capture the driver's trunk status write, which would hit the DB."""
    return mocker.patch.object(trunk, "update")


SESSION = object()


@pytest.fixture
def subport_binding(mocker):
    """Capture the driver's writes to the subport's binding rows.

    The driver writes every subport in one admin session, which SESSION stands in for.
    """
    mocker.patch(
        "neutron_understack.utils.get_admin_session",
        return_value=contextlib.nullcontext(SESSION),
    )
    return mocker.patch.multiple(
        "neutron_understack.utils",
        set_subports_trunk_binding=mocker.DEFAULT,
        clear_subports_trunk_binding=mocker.DEFAULT,
    )


@pytest.fixture
def subport_fields(mocker, subport_binding):
    """Capture the driver's writes to the subport's port row."""
    return mocker.patch(
        "neutron_understack.utils.update_port_fields_if_owner",
        side_effect=lambda session, port_ids, fields, owner, **kwargs: list(port_ids),
    )


def assert_subport_owned(subport_fields, subport, status):
    subport_fields.assert_called_once_with(
        SESSION,
        [subport["port_id"]],
        {"device_owner": trunk_consts.TRUNK_SUBPORT_OWNER, "status": status},
        trunk_consts.TRUNK_SUBPORT_OWNER,
    )


def assert_subport_binding_set(subport_binding, trunk, subport, vif_type):
    subport_binding["set_subports_trunk_binding"].assert_called_once_with(
        SESSION,
        trunk.port_id,
        {subport["port_id"]: subport["segmentation_id"]},
        vif_type,
    )


def assert_subport_released(subport_fields, subport, subport_binding=None):
    subport_fields.assert_called_once_with(
        SESSION,
        [subport["port_id"]],
        {"device_owner": "", "status": p_const.PORT_STATUS_DOWN},
        trunk_consts.TRUNK_SUBPORT_OWNER,
        include_unowned=False,
    )
    if subport_binding is not None:
        subport_binding["clear_subports_trunk_binding"].assert_called_once_with(
            SESSION, [subport["port_id"]]
        )


@pytest.fixture
def _bound_parent(mocker, port_object):
    mocker.patch("neutron_understack.utils.fetch_port_object", return_value=port_object)
    mocker.patch("neutron_understack.utils.parent_port_is_bound", return_value=True)


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

    @pytest.mark.usefixtures("_bound_parent")
    def test_subports_add_post(
        self,
        understack_trunk_driver,
        trunk_payload,
        subport,
        trunk_status,
        subport_fields,
        subport_binding,
        trunk,
    ):
        understack_trunk_driver.subports_added_post(None, None, None, trunk_payload)

        trunk_status.assert_called_once_with(status=trunk_consts.TRUNK_DOWN_STATUS)
        assert_subport_owned(subport_fields, subport, p_const.PORT_STATUS_DOWN)
        assert_subport_binding_set(
            subport_binding, trunk, subport, portbindings.VIF_TYPE_UNBOUND
        )

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


@pytest.mark.usefixtures("_bound_parent")
class TestSubportsDeleted:
    def test_that_clean_parent_port_is_triggered(
        self,
        mocker,
        port_object,
        understack_trunk_driver,
        trunk_payload,
        trunk,
        subport,
        trunk_status,
        subport_fields,
    ):
        mocker.patch.object(
            understack_trunk_driver, "_clean_parent_port_switchport_config"
        )

        understack_trunk_driver.subports_deleted("", "", "", trunk_payload)

        (
            understack_trunk_driver._clean_parent_port_switchport_config.assert_called_once_with(
                port_object, [subport]
            )
        )

    def test_that_the_subport_is_released(
        self,
        mocker,
        understack_trunk_driver,
        trunk_payload,
        subport,
        trunk_status,
        subport_fields,
        subport_binding,
    ):
        mocker.patch.object(
            understack_trunk_driver, "_clean_parent_port_switchport_config"
        )

        understack_trunk_driver.subports_deleted("", "", "", trunk_payload)

        assert_subport_released(subport_fields, subport, subport_binding)
        trunk_status.assert_not_called()


@pytest.mark.usefixtures("_bound_parent")
class TestTrunkDeleted:
    def test_when_subports_are_present(
        self,
        mocker,
        port_object,
        understack_trunk_driver,
        trunk_payload,
        trunk,
        subport,
        subport_fields,
        subport_binding,
    ):
        mocker.patch.object(
            understack_trunk_driver, "_clean_parent_port_switchport_config"
        )

        understack_trunk_driver.trunk_deleted("", "", "", trunk_payload)

        (
            understack_trunk_driver._clean_parent_port_switchport_config.assert_called_once_with(
                port_object, [subport]
            )
        )
        # The trunk row is gone, so there is no status to record; the ports the
        # trunk owned are handed back.
        assert_subport_released(subport_fields, subport, subport_binding)

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

        understack_trunk_driver._clean_parent_port_switchport_config(
            port_object, [subport]
        )

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

        understack_trunk_driver._clean_parent_port_switchport_config(
            port_object, [subport]
        )

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


class TestTrunkStatus:
    """The trunk driver claims ports DOWN before reconciliation is requested."""

    @pytest.mark.usefixtures("_bound_parent")
    def test_created_trunk_on_a_bound_parent_starts_down(
        self,
        understack_trunk_driver,
        trunk_payload,
        subport,
        trunk_status,
        subport_fields,
        subport_binding,
        trunk,
    ):
        understack_trunk_driver.trunk_created_post(None, None, None, trunk_payload)

        trunk_status.assert_called_once_with(status=trunk_consts.TRUNK_DOWN_STATUS)
        assert_subport_owned(subport_fields, subport, p_const.PORT_STATUS_DOWN)
        assert_subport_binding_set(
            subport_binding, trunk, subport, portbindings.VIF_TYPE_UNBOUND
        )

    def test_created_trunk_on_an_unbound_parent_stays_down(
        self,
        mocker,
        understack_trunk_driver,
        trunk_payload,
        port_object,
        subport,
        trunk_status,
        subport_fields,
        subport_binding,
        trunk,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )
        mocker.patch(
            "neutron_understack.utils.parent_port_is_bound", return_value=False
        )

        understack_trunk_driver.trunk_created_post(None, None, None, trunk_payload)

        trunk_status.assert_called_once_with(status=trunk_consts.TRUNK_DOWN_STATUS)
        # Still this trunk's subport, just not carried by any switch yet.
        assert_subport_owned(subport_fields, subport, p_const.PORT_STATUS_DOWN)
        assert_subport_binding_set(
            subport_binding, trunk, subport, portbindings.VIF_TYPE_UNBOUND
        )

    def test_a_trunk_on_a_non_baremetal_parent_is_left_to_ovn(
        self,
        mocker,
        understack_trunk_driver,
        trunk_payload,
        port_object,
        trunk_status,
        subport_fields,
        subport_binding,
    ):
        port_object.bindings[0].vnic_type = portbindings.VNIC_NORMAL
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )

        understack_trunk_driver.trunk_created_post(None, None, None, trunk_payload)

        trunk_status.assert_not_called()
        subport_fields.assert_not_called()
        subport_binding["set_subports_trunk_binding"].assert_not_called()


class TestClaimSubports:
    def test_the_trunk_itself_is_not_written(
        self, trunk, subport, trunk_status, subport_fields, subport_binding
    ):
        claim_subports(trunk.port_id, [subport], trunk_consts.TRUNK_ACTIVE_STATUS)

        assert_subport_owned(subport_fields, subport, p_const.PORT_STATUS_ACTIVE)
        assert_subport_binding_set(
            subport_binding, trunk, subport, portbindings.VIF_TYPE_OTHER
        )
        trunk_status.assert_not_called()


class TestUpdateTrunkState:
    def test_an_active_trunk_binds_its_subports_to_the_switchport(
        self, trunk, subport, trunk_status, subport_fields, subport_binding
    ):
        update_trunk_state(trunk, [subport], trunk_consts.TRUNK_ACTIVE_STATUS)

        assert_subport_owned(subport_fields, subport, p_const.PORT_STATUS_ACTIVE)
        assert_subport_binding_set(
            subport_binding, trunk, subport, portbindings.VIF_TYPE_OTHER
        )

    def test_a_subport_owned_by_another_service_is_left_alone(
        self, trunk, subport, trunk_status, subport_fields, subport_binding
    ):
        subport_fields.side_effect = None
        subport_fields.return_value = []

        update_trunk_state(trunk, [subport], trunk_consts.TRUNK_ACTIVE_STATUS)

        subport_binding["set_subports_trunk_binding"].assert_not_called()


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
        check_native_vlan = mocker.patch.object(
            understack_trunk_driver, "check_trunk_native_vlan"
        )
        trunk_details = {"trunk_id": "trunk-a", "sub_ports": []}

        understack_trunk_driver.configure_trunk(
            trunk_details=trunk_details,
            port_id=port_id,
            physical_network="physnet-a",
            native_vlan_id=1800,
        )

        check_native_vlan.assert_called_once_with(
            trunk_details=trunk_details,
            physical_network="physnet-a",
            native_vlan_id=1800,
        )
        understack_trunk_driver._add_subports_networks_to_parent_port_switchport.assert_called_once_with(
            parent_port=port_object,
            subports=[],
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


class TestCheckSubportsSegmentationId:
    def test_when_trunk_id_is_network_node_trunk_id(
        self,
        mocker,
        understack_trunk_driver,
        trunk_id,
        port_object,
    ):
        mocker.patch(
            "neutron_understack.utils.fetch_network_node_trunk_id",
            return_value=str(trunk_id),
        )
        find_segment = mocker.patch(
            "neutron_understack.utils.network_segment_by_physnet"
        )

        result = understack_trunk_driver._check_subports_segmentation_id(
            [], str(trunk_id), port_object
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
        subport.segmentation_id = 4000

        result = understack_trunk_driver._check_subports_segmentation_id(
            [subport], trunk_id, port_object
        )

        find_segment.assert_called_once_with(
            network_id=str(network_id), physnet="physnet"
        )
        assert result is None

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

        with pytest.raises(SubportSegmentationIDError, match="used as both"):
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

        understack_trunk_driver._clean_parent_port_switchport_config(
            port_object, [subport]
        )

        deallocate.assert_called_once_with([subport], str(host_id))
