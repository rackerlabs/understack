"""Unit tests for the netdev-router reconciler periodic.

Registration tests use Neutron's maintenance discovery. Reconciliation tests
inject the client and lock state to isolate the scan logic.
"""

from types import SimpleNamespace

import pytest
from keystoneauth1.exceptions import NoMatchingPlugin
from neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb import maintenance
from openstack.baremetal.v1.node import Node
from oslo_config import cfg
from oslo_config import fixture as config_fixture

from neutron_understack import config as understack_config
from neutron_understack.maintenance import NetdevRouterMaintenancePeriodics


@pytest.fixture
def reconcile_conf():
    conf = config_fixture.Config(cfg.CONF)
    conf.setUp()
    understack_config.register_netdev_reconcile_opts(cfg.CONF)
    yield conf
    conf.cleanUp()


@pytest.fixture
def uninitialized_periodics(mocker, reconcile_conf):
    idl = SimpleNamespace(has_lock=True, set_lock=mocker.Mock())
    ovn_client = SimpleNamespace(_nb_idl=SimpleNamespace(idl=idl))
    return NetdevRouterMaintenancePeriodics(plugin=None, ovn_client=ovn_client)


class TestClientInitialization:
    @pytest.mark.parametrize("enabled", [True, False])
    def test_registration_does_not_initialize_ironic(
        self, mocker, reconcile_conf, uninitialized_periodics, enabled
    ):
        reconcile_conf.config(group="netdev_router_reconcile", enabled=enabled)
        constructor = mocker.patch(
            "neutron_understack.maintenance.IronicClient",
            side_effect=NoMatchingPlugin("invalid-auth-plugin"),
        )
        worker = maintenance.MaintenanceThread()

        worker.add_periodics(uninitialized_periodics)

        constructor.assert_not_called()
        assert [callback for callback, _, _ in worker._callables] == [
            uninitialized_periodics.reconcile_netdev_routers
        ]
        if not enabled:
            uninitialized_periodics.reconcile_netdev_routers()
            constructor.assert_not_called()

    def test_initialization_failure_is_retried_on_next_pass(
        self, mocker, reconcile_conf, uninitialized_periodics
    ):
        reconcile_conf.config(group="netdev_router_reconcile", enabled=True)
        client = mocker.Mock()
        client.panos_reconcile_nodes.return_value = []
        constructor = mocker.patch(
            "neutron_understack.maintenance.IronicClient",
            side_effect=[NoMatchingPlugin("invalid-auth-plugin"), client],
        )
        mocker.patch("neutron_understack.maintenance.n_context.get_admin_context")
        obj = uninitialized_periodics
        obj._orphans_seen = {("n1", "r1")}

        obj.reconcile_netdev_routers()

        assert obj._orphans_seen == set()
        client.panos_reconcile_nodes.assert_not_called()

        obj.reconcile_netdev_routers()
        obj.reconcile_netdev_routers()

        assert constructor.call_count == 2
        assert client.panos_reconcile_nodes.call_count == 2
        client.release_orphan_node.assert_not_called()


def _node(mocker, node_id, router_id, extra=None):
    return Node(id=node_id, instance_id=router_id, extra={} if extra is None else extra)


def _periodics(mocker, nodes=(), live_router_ids=()):
    """Build a reconciler with Ironic and the Neutron router table mocked."""
    obj = NetdevRouterMaintenancePeriodics.__new__(NetdevRouterMaintenancePeriodics)
    obj._orphans_seen = set()
    obj._idl = mocker.Mock(has_lock=True)
    obj._ironic_ref = mocker.Mock()
    obj._ironic_ref.panos_reconcile_nodes.return_value = list(nodes)
    obj._ironic_ref.release_orphan_node.return_value = True

    mocker.patch("neutron_understack.maintenance.n_context.get_admin_context")
    live = set(live_router_ids)
    mocker.patch(
        "neutron_understack.maintenance.l3_obj.Router.objects_exist",
        side_effect=lambda context, id: id in live,
    )
    return obj


def _released_router_ids(obj):
    return [call.args[1] for call in obj._ironic_ref.release_orphan_node.call_args_list]


class TestOrphanConfirmation:
    def test_first_sighting_only_defers(self, mocker, reconcile_conf):
        # Adoption stamps instance_uuid before the router row exists, so a
        # router being created right now looks exactly like an orphan. One
        # sighting must never be enough to release.
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])

        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == {("n1", "r1")}

    def test_second_sighting_releases(self, mocker, reconcile_conf):
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])

        obj._reconcile_once()
        obj._reconcile_once()

        assert _released_router_ids(obj) == ["r1"]

    def test_live_router_node_is_never_touched(self, mocker, reconcile_conf):
        obj = _periodics(
            mocker, nodes=[_node(mocker, "n1", "r1")], live_router_ids=["r1"]
        )

        obj._reconcile_once()
        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == set()

    def test_router_appearing_between_passes_disarms_the_node(
        self, mocker, reconcile_conf
    ):
        # The in-flight create completes between passes: the sighting from the
        # first pass must not survive to authorize a release.
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])
        obj._reconcile_once()

        mocker.patch(
            "neutron_understack.maintenance.l3_obj.Router.objects_exist",
            return_value=True,
        )
        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == set()

    def test_readopted_node_must_be_reconfirmed(self, mocker, reconcile_conf):
        # n1 looked orphaned holding r1; by the next pass it has been freed and
        # re-adopted by r2, whose router row is still being inserted. Keying the
        # sighting on the node alone would release r2's in-flight adoption.
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])
        obj._reconcile_once()

        obj._ironic_ref.panos_reconcile_nodes.return_value = [_node(mocker, "n1", "r2")]
        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == {("n1", "r2")}

    def test_node_without_a_stamp_is_ignored(self, mocker, reconcile_conf):
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", None)])

        obj._reconcile_once()
        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == set()

    def test_marker_only_node_is_reconciled(self, mocker, reconcile_conf):
        obj = _periodics(
            mocker,
            nodes=[
                _node(
                    mocker,
                    "n1",
                    None,
                    extra={"understack_router_release": "r1"},
                )
            ],
        )

        obj._reconcile_once()
        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_called_once_with("n1", "r1")

    def test_conflicting_marker_is_ignored(self, mocker, reconcile_conf):
        obj = _periodics(
            mocker,
            nodes=[
                _node(
                    mocker,
                    "n1",
                    "r2",
                    extra={"understack_router_release": "r1"},
                )
            ],
        )

        obj._reconcile_once()
        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == set()

    def test_only_the_orphans_are_released(self, mocker, reconcile_conf):
        obj = _periodics(
            mocker,
            nodes=[
                _node(mocker, "n1", "live"),
                _node(mocker, "n2", "gone"),
                _node(mocker, "n3", "also-gone"),
            ],
            live_router_ids=["live"],
        )

        obj._reconcile_once()
        obj._reconcile_once()

        assert sorted(_released_router_ids(obj)) == ["also-gone", "gone"]


class TestReleaseFailureHandling:
    def test_router_reappearing_before_release_disarms_candidate(
        self, mocker, reconcile_conf
    ):
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])
        exists = mocker.patch(
            "neutron_understack.maintenance.l3_obj.Router.objects_exist"
        )
        exists.side_effect = [False, False, True]

        obj._reconcile_once()
        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == set()

    def test_one_failing_node_does_not_stop_the_sweep(self, mocker, reconcile_conf):
        obj = _periodics(
            mocker,
            nodes=[_node(mocker, "n1", "r1"), _node(mocker, "n2", "r2")],
        )
        obj._ironic_ref.release_orphan_node.side_effect = [
            RuntimeError("ironic down"),
            True,
        ]

        obj._reconcile_once()
        obj._reconcile_once()

        assert _released_router_ids(obj) == ["r1", "r2"]

    def test_failed_release_stays_a_candidate(self, mocker, reconcile_conf):
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])
        obj._ironic_ref.release_orphan_node.side_effect = RuntimeError("boom")

        obj._reconcile_once()
        obj._reconcile_once()

        # Still orphaned and still armed, so the next pass retries.
        assert obj._orphans_seen == {("n1", "r1")}

    def test_incomplete_release_stays_a_candidate(self, mocker, reconcile_conf):
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])
        obj._ironic_ref.release_orphan_node.return_value = False
        obj._ironic_ref.release_orphan_node.side_effect = None

        obj._reconcile_once()
        obj._reconcile_once()

        assert _released_router_ids(obj) == ["r1"]
        assert obj._orphans_seen == {("n1", "r1")}
        obj._reconcile_once()
        assert _released_router_ids(obj) == ["r1", "r1"]


class TestConfigGates:
    def test_dry_run_reports_without_releasing(self, mocker, reconcile_conf):
        reconcile_conf.config(group="netdev_router_reconcile", dry_run=True)
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])

        obj._reconcile_once()
        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == {("n1", "r1")}

    def test_disabled_does_not_even_query_ironic(self, mocker, reconcile_conf):
        reconcile_conf.config(group="netdev_router_reconcile", enabled=False)
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])
        obj._orphans_seen = {("n1", "r1")}

        obj.reconcile_netdev_routers()

        obj._ironic_ref.panos_reconcile_nodes.assert_not_called()
        assert obj._orphans_seen == set()

    def test_a_failed_pass_never_escapes_the_periodic(self, mocker, reconcile_conf):
        # A failed scan is logged and retried on the next scheduled pass.
        reconcile_conf.config(group="netdev_router_reconcile", enabled=True)
        obj = _periodics(mocker, nodes=[])
        obj._orphans_seen = {("n1", "r1")}
        obj._ironic_ref.panos_reconcile_nodes.side_effect = RuntimeError("ironic down")

        obj.reconcile_netdev_routers()

        assert obj._orphans_seen == set()

    def test_enabled_pass_runs_the_sweep(self, mocker, reconcile_conf):
        reconcile_conf.config(group="netdev_router_reconcile", enabled=True)
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])

        obj.reconcile_netdev_routers()

        obj._ironic_ref.panos_reconcile_nodes.assert_called_once_with()

    def test_lost_lock_before_release_clears_confirmation(self, mocker, reconcile_conf):
        obj = _periodics(mocker, nodes=[_node(mocker, "n1", "r1")])
        obj._reconcile_once()
        obj._idl.has_lock = False

        obj._reconcile_once()

        obj._ironic_ref.release_orphan_node.assert_not_called()
        assert obj._orphans_seen == set()
