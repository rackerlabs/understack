import logging
from unittest.mock import MagicMock

import pytest
from neutron_lib import constants as p_const
from neutron_lib import exceptions as exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import events
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import resources
from neutron_lib.plugins.ml2 import api

from neutron_understack import undersync_mech
from neutron_understack.undersync_mech import UndersyncDriver


def _make_context(vnic_type=portbindings.VNIC_BAREMETAL, segments=None):
    context = MagicMock()
    context.current = {"id": "port-1", portbindings.VNIC_TYPE: vnic_type}
    context.segments_to_bind = segments or []
    return context


@pytest.fixture
def vlan_segment():
    def _make(segment_id="seg-vlan-1"):
        return {
            api.ID: segment_id,
            api.NETWORK_TYPE: p_const.TYPE_VLAN,
            api.SEGMENTATION_ID: 100,
            api.PHYSICAL_NETWORK: "physnet1",
            api.MTU: 1500,
        }

    return _make


@pytest.fixture
def vxlan_segment():
    def _make(segment_id="seg-vxlan-1"):
        return {
            api.ID: segment_id,
            api.NETWORK_TYPE: p_const.TYPE_VXLAN,
            api.SEGMENTATION_ID: 1000,
            api.PHYSICAL_NETWORK: None,
            api.MTU: 1450,
        }

    return _make


class TestUndersyncDriverBindPort:
    def test_binds_vlan_segment(self, undersync_driver, vlan_segment):
        seg = vlan_segment()
        ctx = _make_context(segments=[seg])

        undersync_driver.bind_port(ctx)

        ctx.set_binding.assert_called_once_with(
            segment_id=seg[api.ID],
            vif_type=portbindings.VIF_TYPE_OTHER,
            vif_details={},
            status=p_const.PORT_STATUS_ACTIVE,
        )

    def test_binds_first_vlan_segment_only(self, undersync_driver, vlan_segment):
        seg1 = vlan_segment("seg-vlan-1")
        seg2 = vlan_segment("seg-vlan-2")
        ctx = _make_context(segments=[seg1, seg2])

        undersync_driver.bind_port(ctx)

        ctx.set_binding.assert_called_once_with(
            segment_id=seg1[api.ID],
            vif_type=portbindings.VIF_TYPE_OTHER,
            vif_details={},
            status=p_const.PORT_STATUS_ACTIVE,
        )

    def test_skips_vxlan_segment(self, undersync_driver, vxlan_segment):
        ctx = _make_context(segments=[vxlan_segment()])

        undersync_driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_skips_unsupported_vnic_type(self, undersync_driver, vlan_segment):
        ctx = _make_context(vnic_type="direct", segments=[vlan_segment()])

        undersync_driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_normal_vnic_type_is_not_supported(self, undersync_driver, vlan_segment):
        ctx = _make_context(
            vnic_type=portbindings.VNIC_NORMAL, segments=[vlan_segment()]
        )

        undersync_driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_binds_vlan_when_preceded_by_vxlan(
        self, undersync_driver, vxlan_segment, vlan_segment
    ):
        vlan = vlan_segment()
        ctx = _make_context(segments=[vxlan_segment(), vlan])

        undersync_driver.bind_port(ctx)

        ctx.set_binding.assert_called_once_with(
            segment_id=vlan[api.ID],
            vif_type=portbindings.VIF_TYPE_OTHER,
            vif_details={},
            status=p_const.PORT_STATUS_ACTIVE,
        )

    def test_empty_segments_to_bind(self, undersync_driver):
        ctx = _make_context(segments=[])

        undersync_driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_skips_direct_vnic_type(self, undersync_driver, vlan_segment):
        ctx = _make_context(
            vnic_type=portbindings.VNIC_DIRECT, segments=[vlan_segment()]
        )

        undersync_driver.bind_port(ctx)

        ctx.set_binding.assert_not_called()

    def test_logs_warning_when_no_vlan_segment_found(
        self, undersync_driver, vxlan_segment, caplog
    ):
        ctx = _make_context(segments=[vxlan_segment()])

        undersync_driver.bind_port(ctx)

        assert "no VLAN segment found" in caplog.text
        ctx.set_binding.assert_not_called()


class TestInitialize:
    def test_builds_the_client_from_the_configured_url(self, mocker, oslo_config):
        oslo_config.config(
            undersync_url="http://undersync.example:8080", group="ml2_understack"
        )
        undersync_cls = mocker.patch("neutron_understack.undersync_mech.Undersync")

        UndersyncDriver().initialize()

        undersync_cls.assert_called_once_with("http://undersync.example:8080")

    def test_undersync_client_uses_the_ironic_keystone_session(self, mocker):
        """The client borrows the [ironic] credentials rather than its own."""
        session = mocker.MagicMock()
        get_session = mocker.patch(
            "neutron_understack.config.get_session", return_value=session
        )

        driver = UndersyncDriver()
        driver.initialize()

        get_session.assert_called_once_with("ironic")
        assert driver.undersync._session == session

    def test_subscribes_to_the_trunk_events(self, mocker):
        mocker.patch("neutron_understack.undersync_mech.Undersync")
        subscribe = mocker.patch("neutron_understack.undersync_mech.registry.subscribe")

        UndersyncDriver().initialize()

        subscribed = {(call.args[1], call.args[2]) for call in subscribe.call_args_list}
        assert subscribed == {
            (resources.SUBPORTS, events.PRECOMMIT_DELETE),
            (resources.TRUNK, events.PRECOMMIT_DELETE),
            (resources.SUBPORTS, events.AFTER_CREATE),
            (resources.SUBPORTS, events.AFTER_DELETE),
            (resources.TRUNK, events.AFTER_DELETE),
        }

    def test_every_subscription_is_cancellable(self, mocker):
        """An UndersyncError must abort the request, not be swallowed.

        neutron-lib only re-raises from a postcommit event when the callback
        was subscribed cancellable, so dropping this silently loses failures.
        """
        mocker.patch("neutron_understack.undersync_mech.Undersync")
        subscribe = mocker.patch("neutron_understack.undersync_mech.registry.subscribe")

        UndersyncDriver().initialize()

        assert all(call.kwargs["cancellable"] for call in subscribe.call_args_list)

    def test_after_hooks_run_later_than_the_understack_trunk_driver(self, mocker):
        """The trunk driver subscribes at PRIORITY_DEFAULT and must go first."""
        mocker.patch("neutron_understack.undersync_mech.Undersync")
        subscribe = mocker.patch("neutron_understack.undersync_mech.registry.subscribe")

        UndersyncDriver().initialize()

        after_hooks = [
            call
            for call in subscribe.call_args_list
            if call.args[2] != events.PRECOMMIT_DELETE
        ]
        assert after_hooks
        assert all(
            call.kwargs["priority"] > priority_group.PRIORITY_DEFAULT
            for call in after_hooks
        )


class TestUpdatePortPostcommit:
    def test_syncs_when_the_port_is_bound(
        self, undersync_driver, undersync_client, port_context
    ):
        undersync_driver.update_port_postcommit(port_context)

        undersync_client.sync.assert_called_once_with("physnet")

    def test_syncs_when_the_port_is_unbound(
        self, undersync_driver, undersync_client, port_context
    ):
        port_context._binding.vif_type = portbindings.VIF_TYPE_UNBOUND

        undersync_driver.update_port_postcommit(port_context)

        undersync_client.sync.assert_called_once_with("physnet")

    def test_reads_the_physnet_from_the_original_port_when_unbinding(
        self, undersync_driver, undersync_client, port_context
    ):
        """Only ``original`` still carries a binding profile once unbound."""
        port_context._binding.vif_type = portbindings.VIF_TYPE_UNBOUND
        port_context.current[portbindings.PROFILE] = {
            "physical_network": "physnet-current"
        }
        port_context.original[portbindings.PROFILE] = {
            "physical_network": "physnet-original"
        }

        undersync_driver.update_port_postcommit(port_context)

        undersync_client.sync.assert_called_once_with("physnet-original")

    @pytest.mark.parametrize(
        "binding_profile", [{"physical_network": None}], indirect=True
    )
    def test_does_not_sync_without_a_physnet(
        self, undersync_driver, undersync_client, port_context
    ):
        undersync_driver.update_port_postcommit(port_context)

        undersync_client.sync.assert_not_called()

    def test_skips_non_baremetal_ports(
        self, undersync_driver, undersync_client, port_context
    ):
        port_context.current[portbindings.VNIC_TYPE] = portbindings.VNIC_NORMAL

        undersync_driver.update_port_postcommit(port_context)

        undersync_client.sync.assert_not_called()

    def test_does_not_sync_a_port_that_was_never_bound(
        self, undersync_driver, undersync_client, port_context
    ):
        port_context._binding.vif_type = portbindings.VIF_TYPE_UNBOUND
        port_context._original_vif_type = portbindings.VIF_TYPE_UNBOUND

        undersync_driver.update_port_postcommit(port_context)

        undersync_client.sync.assert_not_called()


class TestDeletePortPostcommit:
    def test_syncs_the_ports_vlan_group(
        self, undersync_driver, undersync_client, port_context
    ):
        undersync_driver.delete_port_postcommit(port_context)

        undersync_client.sync.assert_called_once_with("physnet")

    @pytest.mark.parametrize(
        "binding_profile", [{"physical_network": None}], indirect=True
    )
    def test_does_not_sync_without_a_physnet(
        self, undersync_driver, undersync_client, port_context
    ):
        undersync_driver.delete_port_postcommit(port_context)

        undersync_client.sync.assert_not_called()

    def test_skips_non_baremetal_ports(
        self, undersync_driver, undersync_client, port_context
    ):
        port_context.current[portbindings.VNIC_TYPE] = portbindings.VNIC_NORMAL

        undersync_driver.delete_port_postcommit(port_context)

        undersync_client.sync.assert_not_called()


@pytest.mark.usefixtures("_bound_parent_port")
class TestTrunkEventHandlers:
    @pytest.fixture
    def _bound_parent_port(self, mocker, port_object) -> None:
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )

    @pytest.mark.parametrize(
        "handler_name",
        ["_subports_after_create", "_subports_after_delete", "_trunk_after_delete"],
    )
    def test_syncs_the_parent_ports_vlan_group(
        self, mocker, undersync_driver, undersync_client, trunk, handler_name
    ):
        handler = getattr(undersync_driver, handler_name)

        handler(None, None, None, mocker.Mock(states=[trunk]))

        undersync_client.sync.assert_called_once_with("physnet")

    @pytest.mark.parametrize(
        "handler_name",
        ["_subports_after_create", "_subports_after_delete", "_trunk_after_delete"],
    )
    def test_does_not_sync_when_the_parent_port_is_unbound(
        self,
        mocker,
        undersync_driver,
        undersync_client,
        trunk,
        port_object,
        handler_name,
    ):
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        handler = getattr(undersync_driver, handler_name)

        handler(None, None, None, mocker.Mock(states=[trunk]))

        undersync_client.sync.assert_not_called()

    def test_trunk_delete_without_subports_does_nothing(
        self, mocker, undersync_driver, undersync_client, trunk
    ):
        trunk.sub_ports = []
        fetch = mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=None
        )

        undersync_driver._trunk_after_delete(
            None, None, None, mocker.Mock(states=[trunk])
        )

        undersync_client.sync.assert_not_called()
        fetch.assert_not_called()

    @pytest.mark.parametrize(
        "binding_profile", [{"physical_network": None}], indirect=True
    )
    def test_logs_instead_of_raising_when_the_physnet_is_missing(
        self, mocker, caplog, undersync_driver, undersync_client, trunk
    ):
        """This runs postcommit, so raising would only surface as a 500."""
        caplog.set_level(logging.ERROR, logger=undersync_mech.LOG.name)

        undersync_driver._subports_after_delete(
            None, None, None, mocker.Mock(states=[trunk])
        )

        assert "physical_network is required" in caplog.text
        undersync_client.sync.assert_not_called()


class TestValidateParentPhysnet:
    @pytest.fixture
    def _bound_parent_port(self, mocker, port_object) -> None:
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )

    @pytest.mark.usefixtures("_bound_parent_port")
    @pytest.mark.parametrize("resource", [resources.SUBPORTS, resources.TRUNK])
    def test_accepts_a_parent_port_with_a_physnet(
        self, mocker, undersync_driver, trunk, resource
    ):
        undersync_driver._validate_parent_physnet(
            resource, events.PRECOMMIT_DELETE, None, mocker.Mock(states=[trunk])
        )

    @pytest.mark.usefixtures("_bound_parent_port")
    @pytest.mark.parametrize("resource", [resources.SUBPORTS, resources.TRUNK])
    @pytest.mark.parametrize(
        "binding_profile", [{"physical_network": None}], indirect=True
    )
    def test_rejects_a_parent_port_without_a_physnet(
        self, mocker, undersync_driver, trunk, resource
    ):
        with pytest.raises(exc.BadRequest, match="physical_network is required"):
            undersync_driver._validate_parent_physnet(
                resource, events.PRECOMMIT_DELETE, None, mocker.Mock(states=[trunk])
            )

    @pytest.mark.parametrize(
        "binding_profile", [{"physical_network": None}], indirect=True
    )
    def test_ignores_an_unbound_parent_port(
        self, mocker, undersync_driver, trunk, port_object
    ):
        """An unbound parent has no switchport config, so nothing can leak."""
        port_object.bindings[0].vif_type = portbindings.VIF_TYPE_UNBOUND
        mocker.patch(
            "neutron_understack.utils.fetch_port_object", return_value=port_object
        )

        undersync_driver._validate_parent_physnet(
            resources.SUBPORTS,
            events.PRECOMMIT_DELETE,
            None,
            mocker.Mock(states=[trunk]),
        )

    def test_ignores_a_trunk_with_no_subports(self, mocker, undersync_driver, trunk):
        """Never fetches the port: there is no switchport config to protect."""
        trunk.sub_ports = []
        fetch = mocker.patch("neutron_understack.utils.fetch_port_object")

        undersync_driver._validate_parent_physnet(
            resources.TRUNK,
            events.PRECOMMIT_DELETE,
            None,
            mocker.Mock(states=[trunk]),
        )

        fetch.assert_not_called()
