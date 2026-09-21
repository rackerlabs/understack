"""Unit tests for the IronicClient adopt/release state handling.

IronicClient.__init__ needs Ironic config, so these bypass it with __new__ and
inject a mock ``irclient`` (the openstacksdk baremetal proxy).
"""

import pytest
from openstack.baremetal.v1.node import Node

from neutron_understack.ironic import IronicClient
from neutron_understack.ironic import NodeReleaseResult

_DEFAULT_EXTRA = object()


def _node(
    node_id="n1",
    *,
    state="active",
    router_id="router-1",
    extra=_DEFAULT_EXTRA,
    lessee="project-1",
    instance_name="router-1",
    maintenance=False,
):
    return Node(
        id=node_id,
        driver="panos",
        is_maintenance=maintenance,
        provision_state=state,
        instance_id=router_id,
        instance_name=instance_name,
        lessee=lessee,
        extra={} if extra is _DEFAULT_EXTRA else extra,
    )


def _client(mocker):
    client = IronicClient.__new__(IronicClient)
    client.irclient = mocker.Mock()
    return client


class _FakeBaremetal:
    def __init__(
        self,
        node,
        *,
        fail_undeploy_once=False,
        fail_cleanup_once=False,
        fail_manage_once=False,
    ):
        self.node = node
        self.fail_undeploy_once = fail_undeploy_once
        self.fail_cleanup_once = fail_cleanup_once
        self.fail_manage_once = fail_manage_once

    def _copy(self):
        return Node(**self.node.to_dict())

    def get_node(self, node):
        node_id = node.id if isinstance(node, Node) else node
        if node_id != self.node.id:
            return None
        return self._copy()

    def nodes(self, **filters):
        node = self._copy()
        for key, value in filters.items():
            if key == "details":
                continue
            if key == "associated":
                if bool(node.instance_id) is not value:
                    return iter([])
                continue
            if getattr(node, key) != value:
                return iter([])
        return iter([node])

    def patch_node(self, node, patch, retry_on_conflict=False):
        if self.fail_cleanup_once and any(
            op["path"] == "/extra/understack_router_release" and op["op"] == "remove"
            for op in patch
        ):
            self.fail_cleanup_once = False
            raise RuntimeError("cleanup failed")
        for op in patch:
            path = op["path"]
            if path == "/instance_uuid":
                self.node.instance_id = op["value"]
            elif path == "/instance_name":
                self.node.instance_name = op["value"]
            elif path == "/lessee":
                self.node.lessee = op["value"]
            elif path.startswith("/extra/"):
                key = path.removeprefix("/extra/")
                extra = dict(self.node.extra or {})
                if op["op"] == "remove":
                    extra.pop(key, None)
                else:
                    extra[key] = op["value"]
                self.node.extra = extra

    def set_node_provision_state(self, node, target, wait=True, timeout=None):
        if target == "manage":
            self.node.provision_state = "manageable"
            if self.fail_manage_once:
                self.fail_manage_once = False
                raise RuntimeError("manage response lost")
        elif target == "deleted":
            self.node.instance_id = None
            self.node.instance_name = None
            if self.fail_undeploy_once:
                self.fail_undeploy_once = False
                self.node.provision_state = "error"
                raise RuntimeError("undeploy failed")
            self.node.provision_state = "available"
        elif target == "provide":
            self.node.provision_state = "available"
        elif target == "adopt":
            self.node.provision_state = "active"
        return self._copy()

    def update_node(self, node, retry_on_conflict=False, **fields):
        for name, value in fields.items():
            setattr(self.node, name, value)
        return self._copy()

    def wait_for_nodes_provision_state(self, nodes, state, timeout=None):
        self.node.provision_state = state
        return [self._copy()]


def _release_sequence(
    client,
    *,
    initial_state="active",
    transition_target="available",
    router_id="router-1",
):
    marker = {"understack_router_release": router_id}
    states = [
        _node(state=initial_state, router_id=router_id),
        _node(state=initial_state, router_id=router_id, extra=marker.copy()),
    ]
    if initial_state != "available":
        states.append(
            _node(state=transition_target, router_id=None, extra=marker.copy())
        )
    states.append(
        _node(
            state="available",
            router_id=None,
            instance_name=None,
            lessee=None,
            extra={},
        )
    )
    client.irclient.get_node.side_effect = states


class TestAdoptRollback:
    def test_manage_failure_is_rolled_back_and_reraised(self, mocker):
        # A manage failure must route through _return_node_to_available and
        # re-raise so the create aborts. The recovery leaves a manageable node
        # parked after clearing ownership.
        client = _client(mocker)
        node = _node(state="available", router_id=None)
        owner = {"understack_router_id": "r"}
        marker = {
            "understack_router_id": "r",
            "understack_router_release": "r",
        }
        client.irclient.get_node.side_effect = [
            # rollback: read state, write release marker, re-read, confirm
            _node(
                state="manageable",
                router_id="r",
                lessee="p",
                instance_name="n",
                extra=owner.copy(),
            ),
            _node(
                state="manageable",
                router_id="r",
                lessee="p",
                instance_name="n",
                extra=marker.copy(),
            ),
            _node(
                state="manageable",
                router_id=None,
                instance_name=None,
                lessee=None,
                extra={},
            ),
        ]
        client.irclient.set_node_provision_state.side_effect = RuntimeError(
            "manage boom"
        )

        with pytest.raises(RuntimeError):
            client.adopt_node_for_router(
                node, project_id="p", router_id="r", router_name="n"
            )

        # the failed manage is the only provision call; recovery parks the node
        assert client.irclient.set_node_provision_state.call_count == 1


class TestVifAttach:
    def test_attach_calls_proxy(self, mocker):
        client = _client(mocker)
        node = _node(state="available", router_id=None)

        client.attach_vif_to_node(node, "port-1")

        client.irclient.attach_vif_to_node.assert_called_once_with(node, "port-1")

    def test_attach_works_on_an_adopted_active_node(self, mocker):
        client = _client(mocker)
        adopted = _node(state="active", router_id="router-1")

        client.attach_vif_to_node(adopted, "parent-1")

        client.irclient.attach_vif_to_node.assert_called_once_with(adopted, "parent-1")

    def test_detach_uses_ignore_missing_and_returns_result(self, mocker):
        client = _client(mocker)
        node = mocker.Mock(id="n1")
        client.irclient.detach_vif_from_node.return_value = True

        result = client.detach_vif_from_node(node, "port-1")

        assert result is True
        client.irclient.detach_vif_from_node.assert_called_once_with(
            node, "port-1", ignore_missing=True
        )

    def test_node_vif_ids(self, mocker):
        client = _client(mocker)
        node = mocker.Mock(id="n1")
        client.irclient.list_node_vifs.return_value = ["p1", "p2"]

        assert client.node_vif_ids(node) == ["p1", "p2"]


class TestReleaseClearsOwnership:
    def test_active_node_is_undeployed_then_ownership_cleared(self, mocker):
        client = _client(mocker)
        node = _node(state="active")
        _release_sequence(client, initial_state="active")

        assert client._return_node_to_available(node, "router-1") is True

        # active -> undeploy ("deleted")
        (_, target), _ = client.irclient.set_node_provision_state.call_args
        assert target == "deleted"
        marker_patch, cleanup_patch = (
            call.args[1] for call in client.irclient.patch_node.call_args_list
        )
        assert marker_patch == [
            {
                "op": "add",
                "path": "/extra/understack_router_release",
                "value": "router-1",
            }
        ]
        assert cleanup_patch == [
            {"op": "add", "path": "/lessee", "value": None},
            {"op": "add", "path": "/instance_uuid", "value": None},
            {"op": "add", "path": "/instance_name", "value": None},
            {"op": "remove", "path": "/extra/understack_router_release"},
        ]

    def test_manageable_node_is_marked_then_parked(self, mocker):
        client = _client(mocker)
        node = _node(state="manageable")
        marker = {"understack_router_release": "router-1"}
        client.irclient.get_node.side_effect = [
            node,
            _node(state="manageable", extra=marker.copy()),
            _node(
                state="manageable",
                router_id=None,
                instance_name=None,
                lessee=None,
                extra={},
            ),
        ]

        assert client._return_node_to_available(node, "router-1") is True

        client.irclient.set_node_provision_state.assert_not_called()

    def test_available_node_still_gets_ownership_cleared(self, mocker):
        # e.g. a node left available with a stale lessee from a prior adoption
        client = _client(mocker)
        node = _node(state="available")
        _release_sequence(client, initial_state="available")

        assert client._return_node_to_available(node, "router-1") is True

        client.irclient.set_node_provision_state.assert_not_called()

    def test_adopt_failed_is_managed_then_parked(self, mocker):
        client = _client(mocker)
        node = _node(state="adopt failed")
        marker = {"understack_router_release": "router-1"}
        client.irclient.get_node.side_effect = [
            node,
            _node(state="adopt failed", extra=marker.copy()),
            _node(state="manageable", extra=marker.copy()),
            _node(
                state="manageable",
                router_id=None,
                instance_name=None,
                lessee=None,
                extra={},
            ),
        ]

        assert client._return_node_to_available(node, "router-1") is True

        targets = [
            call.args[1]
            for call in client.irclient.set_node_provision_state.call_args_list
        ]
        assert targets == ["manage"]

    def test_clean_failed_is_managed_then_parked(self, mocker):
        client = _client(mocker)
        node = _node(state="clean failed")
        marker = {"understack_router_release": "router-1"}
        client.irclient.get_node.side_effect = [
            node,
            _node(state="clean failed", extra=marker.copy()),
            _node(state="manageable", extra=marker.copy()),
            _node(
                state="manageable",
                router_id=None,
                instance_name=None,
                lessee=None,
                extra={},
            ),
        ]

        assert client._return_node_to_available(node, "router-1") is True

        targets = [
            call.args[1]
            for call in client.irclient.set_node_provision_state.call_args_list
        ]
        assert targets == ["manage"]

    def test_transient_state_is_left_for_reconciliation(self, mocker):
        client = _client(mocker)
        node = _node(state="adopting")
        client.irclient.get_node.return_value = node

        assert client._return_node_to_available(node, "router-1") is False

        client.irclient.patch_node.assert_not_called()
        client.irclient.set_node_provision_state.assert_not_called()

    def test_failed_undeploy_keeps_marker_for_retry(self, mocker):
        client = _client(mocker)
        node = _node(state="active")
        marker = {"understack_router_release": "router-1"}
        client.irclient.get_node.side_effect = [
            _node(state="active"),
            _node(state="active", extra=marker.copy()),
        ]
        client.irclient.set_node_provision_state.side_effect = RuntimeError("boom")

        assert client._return_node_to_available(node, "router-1") is False

        client.irclient.patch_node.assert_called_once()

    def test_available_node_with_marker_resumes_cleanup(self, mocker):
        client = _client(mocker)
        marker = {"understack_router_release": "router-1"}
        node = _node(state="available", router_id=None, extra=marker.copy())
        client.irclient.get_node.side_effect = [
            node,
            node,
            _node(
                state="available",
                router_id=None,
                instance_name=None,
                lessee=None,
                extra={},
            ),
        ]

        assert client._return_node_to_available(node, "router-1") is True

        client.irclient.set_node_provision_state.assert_not_called()
        cleanup_patch = client.irclient.patch_node.call_args.args[1]
        assert cleanup_patch[-1] == {
            "op": "remove",
            "path": "/extra/understack_router_release",
        }

    def test_null_extra_is_replaced_when_release_marker_is_added(self, mocker):
        client = _client(mocker)
        node = _node(state="active", extra=None)
        marker = {"understack_router_release": "router-1"}
        client.irclient.get_node.side_effect = [
            node,
            _node(state="active", extra=marker.copy()),
            _node(state="available", router_id=None, extra=marker.copy()),
            _node(
                state="available",
                router_id=None,
                instance_name=None,
                lessee=None,
                extra={},
            ),
        ]

        assert client._return_node_to_available(node, "router-1") is True

        marker_patch = client.irclient.patch_node.call_args_list[0].args[1]
        assert marker_patch == [
            {
                "op": "add",
                "path": "/extra",
                "value": {"understack_router_release": "router-1"},
            }
        ]


class TestNodeSelection:
    def test_filters_available_non_maintenance_panos(self, mocker):
        client = _client(mocker)
        node = _node(state="available", router_id=None)
        client.irclient.nodes.return_value = iter([node])

        result = client.available_node_for_resource_class("pa1410")

        assert result is node
        _, kwargs = client.irclient.nodes.call_args
        assert kwargs["driver"] == "panos"
        assert kwargs["resource_class"] == "pa1410"
        assert kwargs["provision_state"] == "available"
        # a node parked in maintenance must never be selected
        assert kwargs["is_maintenance"] is False

    def test_returns_none_when_pool_empty(self, mocker):
        client = _client(mocker)
        client.irclient.nodes.return_value = iter([])

        assert client.available_node_for_resource_class("pa1410") is None

    def test_skips_nodes_reserved_by_pending_release_marker(self, mocker):
        client = _client(mocker)
        client.irclient.nodes.return_value = iter(
            [
                _node(
                    state="available",
                    router_id=None,
                    extra={"understack_router_release": "router-1"},
                ),
                _node(node_id="n2", state="available", router_id=None),
            ]
        )

        assert client.available_node_for_resource_class("pa1410").id == "n2"


class TestReconcileDiscovery:
    def test_scan_is_scoped_to_the_panos_driver(self, mocker):
        # netdev stays the generic type; only panos nodes are ours, and
        # Ironic does that filtering server-side.
        client = _client(mocker)
        bound = _node()
        client.irclient.nodes.return_value = iter([bound])

        assert client.panos_reconcile_nodes() == [bound]
        _, kwargs = client.irclient.nodes.call_args
        assert kwargs["driver"] == "panos"
        assert kwargs["is_maintenance"] is False

    def test_release_marker_alone_is_enough_to_be_a_candidate(self, mocker):
        # Ironic clears instance_uuid on a failed undeploy; the release marker
        # is what keeps a half-released node discoverable.
        client = _client(mocker)
        half_released = _node(
            router_id=None, extra={"understack_router_release": "router-1"}
        )
        client.irclient.nodes.return_value = iter([half_released])

        assert client.panos_reconcile_nodes() == [half_released]

    def test_unbound_unmarked_node_is_not_a_candidate(self, mocker):
        client = _client(mocker)
        free = _node(state="available", router_id=None, lessee=None, instance_name=None)
        client.irclient.nodes.return_value = iter([free])

        assert client.panos_reconcile_nodes() == []


class TestReconcileReleaseRetry:
    def test_failed_undeploy_remains_discoverable_after_ironic_clears_instance(self):
        backend = _FakeBaremetal(_node(state="active"), fail_undeploy_once=True)
        client = IronicClient.__new__(IronicClient)
        client.irclient = backend

        assert client.release_orphan_node("n1", "router-1") is False
        assert backend.node.provision_state == "error"
        assert backend.node.instance_id is None
        assert backend.node.extra == {"understack_router_release": "router-1"}

        restarted_client = IronicClient.__new__(IronicClient)
        restarted_client.irclient = backend
        candidates = restarted_client.panos_reconcile_nodes()

        assert [node.id for node in candidates] == ["n1"]
        assert IronicClient.router_id_for_release(candidates[0]) == "router-1"
        assert restarted_client.release_orphan_node("n1", "router-1") is True
        assert backend.node.provision_state == "available"
        assert backend.node.instance_id is None
        assert backend.node.lessee is None
        assert backend.node.extra == {}

    def test_failed_final_cleanup_keeps_marker_for_next_pass(self):
        backend = _FakeBaremetal(
            _node(
                state="available",
                router_id=None,
                extra={"understack_router_release": "router-1"},
            ),
            fail_cleanup_once=True,
        )
        client = IronicClient.__new__(IronicClient)
        client.irclient = backend

        assert client.release_orphan_node("n1", "router-1") is False
        assert backend.node.extra == {"understack_router_release": "router-1"}

        restarted_client = IronicClient.__new__(IronicClient)
        restarted_client.irclient = backend
        assert restarted_client.release_orphan_node("n1", "router-1") is True
        assert backend.node.extra == {}

    def test_manage_timeout_from_adopt_failed_resumes_with_cleanup(self):
        backend = _FakeBaremetal(
            _node(state="adopt failed"),
            fail_manage_once=True,
        )
        client = IronicClient.__new__(IronicClient)
        client.irclient = backend

        assert client.release_orphan_node("n1", "router-1") is False
        assert backend.node.provision_state == "manageable"
        assert backend.node.extra == {"understack_router_release": "router-1"}

        restarted_client = IronicClient.__new__(IronicClient)
        restarted_client.irclient = backend
        assert restarted_client.release_orphan_node("n1", "router-1") is True
        assert backend.node.provision_state == "manageable"
        assert backend.node.instance_id is None
        assert backend.node.instance_name is None
        assert backend.node.lessee is None
        assert backend.node.extra == {}
        assert restarted_client.panos_reconcile_nodes() == []


class TestReleaseNodeForRouter:
    def test_returns_none_when_no_node_bound(self, mocker):
        client = _client(mocker)
        client.irclient.nodes.return_value = iter([])

        assert client.release_node_for_router("router-1") == NodeReleaseResult(
            node=None, released=False
        )

    def test_releases_bound_node(self, mocker):
        client = _client(mocker)
        node = _node(state="active")
        # node_by_instance_uuid uses irclient.nodes(); _return_node_to_available
        # re-fetches via get_node.
        client.irclient.nodes.return_value = iter([node])
        _release_sequence(client, initial_state="active")

        result = client.release_node_for_router("router-1")

        assert result.node is node
        assert result.released is True
        (_, target), _ = client.irclient.set_node_provision_state.call_args
        assert target == "deleted"

    def test_reports_when_bound_node_release_is_incomplete(self, mocker):
        client = _client(mocker)
        node = _node(state="adopting")
        client.irclient.nodes.return_value = iter([node])
        client.irclient.get_node.return_value = node

        result = client.release_node_for_router("router-1")

        assert result.node is node
        assert result.released is False


class TestOwnershipIsDiscoverableBeforeAnyChange:
    """The marker must land before the node is touched.

    If any step of adoption fails AND the rollback also fails, the marker is
    the only thing that lets reconciliation find the node again. Stamping
    first and marking second leaves a node carrying a router's instance_uuid
    that nothing can discover -- stranded exactly the way this mechanism
    exists to prevent.
    """


class TestLifecycleAgainstStatefulIronic:
    """Whole flows against the stateful fake, not call-order assertions."""

    def _client_for(self, node, **kw):
        client = IronicClient.__new__(IronicClient)
        client.irclient = _FakeBaremetal(node, **kw)
        return client

    def test_create_then_delete_returns_a_clean_node_to_the_pool(self):
        client = self._client_for(
            _node(state="available", router_id=None, lessee=None, instance_name=None)
        )
        client.adopt_node_for_router(
            client.irclient.node,
            project_id="p",
            router_id="r-77",
            router_name="rtr",
        )
        assert client.irclient.node.instance_id == "r-77"

        result = client.release_node_for_router("r-77")

        assert result.released is True
        node = client.irclient.node
        assert node.provision_state == "available"
        assert not node.instance_id
        assert not node.lessee
        assert not node.instance_name
        assert node.extra == {}

    def test_orphan_is_found_and_released_by_the_reconciler_path(self):
        client = self._client_for(
            _node(state="available", router_id=None, lessee=None, instance_name=None)
        )
        client.adopt_node_for_router(
            client.irclient.node,
            project_id="p",
            router_id="r-gone",
            router_name="rtr",
        )

        candidates = client.panos_reconcile_nodes()
        assert [n.id for n in candidates] == ["n1"]
        assert IronicClient.router_id_for_release(candidates[0]) == "r-gone"

        assert client.release_orphan_node("n1", "r-gone") is True
        assert client.irclient.node.provision_state == "available"
        assert client.irclient.node.extra == {}

    def test_a_maintenance_node_is_never_touched(self):
        client = self._client_for(
            _node(
                state="active",
                router_id="r-gone",
                maintenance=True,
                extra={"understack_router_id": "r-gone"},
            )
        )

        assert client.panos_reconcile_nodes() == []
        assert client.release_orphan_node("n1", "r-gone") is False
        assert client.irclient.node.instance_id == "r-gone"


class TestReconcilerTimeout:
    """The reconciler shares one thread with neutron's own OVN periodics.

    A router delete has a caller waiting on it, so it keeps the long API
    timeout. The reconciler does not -- there is another pass shortly -- so it
    must not hold the shared thread for as long.
    """

    def _timeout_used(self, client):
        _, kwargs = client.irclient.set_node_provision_state.call_args
        return kwargs["timeout"]

    def test_reconciler_path_uses_the_short_timeout(self, mocker):
        client = _client(mocker)
        _release_sequence(client, initial_state="active")

        client.release_orphan_node("n1", "router-1")

        assert self._timeout_used(client) == 60

    def test_delete_path_keeps_the_api_timeout(self, mocker):
        client = _client(mocker)
        client.irclient.nodes.return_value = iter([_node(state="active")])
        _release_sequence(client, initial_state="active")

        client.release_node_for_router("router-1")

        assert self._timeout_used(client) == 300
