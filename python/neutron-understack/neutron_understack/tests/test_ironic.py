"""Unit tests for the IronicClient adopt/release state handling.

IronicClient.__init__ needs Ironic config, so these bypass it with __new__ and
inject a mock ``irclient`` (the openstacksdk baremetal proxy).
"""

import pytest

from neutron_understack.ironic import IronicClient


def _client(mocker):
    client = IronicClient.__new__(IronicClient)
    client.irclient = mocker.Mock()
    return client


class TestAdoptRollback:
    def test_manage_failure_is_rolled_back_and_reraised(self, mocker):
        # A manage failure must route through _return_node_to_available (not
        # strand the node in manageable) and re-raise so the create aborts.
        client = _client(mocker)
        node = mocker.Mock(id="n1", provision_state="manageable")
        # 1st set_node_provision_state (manage) raises; the rollback's provide
        # (2nd call) succeeds.
        client.irclient.set_node_provision_state.side_effect = [
            RuntimeError("manage boom"),
            None,
        ]
        client.irclient.get_node.return_value = node

        with pytest.raises(RuntimeError):
            client.adopt_node_for_router(
                node, project_id="p", router_id="r", router_name="n"
            )

        # rollback re-fetched state and tried to return it to available
        client.irclient.get_node.assert_called_once()
        assert (
            client.irclient.set_node_provision_state.call_count == 2
        )  # manage + provide


class TestReleaseClearsOwnership:
    def test_active_node_is_undeployed_then_ownership_cleared(self, mocker):
        client = _client(mocker)
        node = mocker.Mock(id="n1", provision_state="active")
        client.irclient.get_node.return_value = node

        client._return_node_to_available(node)

        # active -> undeploy ("deleted")
        (_, target), _ = client.irclient.set_node_provision_state.call_args
        assert target == "deleted"
        # undeploy leaves lessee, so we must clear ownership afterwards
        _, kwargs = client.irclient.update_node.call_args
        assert kwargs["lessee"] is None
        assert kwargs["instance_id"] is None
        assert kwargs["instance_name"] is None

    def test_manageable_node_is_cleared_then_provided(self, mocker):
        client = _client(mocker)
        node = mocker.Mock(id="n1", provision_state="manageable")
        client.irclient.get_node.return_value = node

        client._return_node_to_available(node)

        client.irclient.update_node.assert_called_once()
        (_, target), _ = client.irclient.set_node_provision_state.call_args
        assert target == "provide"

    def test_available_node_still_gets_ownership_cleared(self, mocker):
        # e.g. a node left available with a stale lessee from a prior adoption
        client = _client(mocker)
        node = mocker.Mock(id="n1", provision_state="available")
        client.irclient.get_node.return_value = node

        client._return_node_to_available(node)

        client.irclient.update_node.assert_called_once()
        client.irclient.set_node_provision_state.assert_not_called()

    def test_unexpected_state_is_left_for_reconciliation(self, mocker):
        client = _client(mocker)
        node = mocker.Mock(id="n1", provision_state="adopt failed")
        client.irclient.get_node.return_value = node

        client._return_node_to_available(node)

        client.irclient.update_node.assert_not_called()
        client.irclient.set_node_provision_state.assert_not_called()


class TestNodeSelection:
    def test_filters_available_non_maintenance_netdev(self, mocker):
        client = _client(mocker)
        node = mocker.Mock(id="n1")
        client.irclient.nodes.return_value = iter([node])

        result = client.available_node_for_resource_class("pa1410")

        assert result is node
        _, kwargs = client.irclient.nodes.call_args
        assert kwargs["driver"] == "netdev"
        assert kwargs["resource_class"] == "pa1410"
        assert kwargs["provision_state"] == "available"
        # a node parked in maintenance must never be selected
        assert kwargs["is_maintenance"] is False

    def test_returns_none_when_pool_empty(self, mocker):
        client = _client(mocker)
        client.irclient.nodes.return_value = iter([])

        assert client.available_node_for_resource_class("pa1410") is None


class TestReleaseNodeForRouter:
    def test_returns_none_when_no_node_bound(self, mocker):
        client = _client(mocker)
        client.irclient.nodes.return_value = iter([])

        assert client.release_node_for_router("router-1") is None

    def test_releases_bound_node(self, mocker):
        client = _client(mocker)
        node = mocker.Mock(id="n1", provision_state="active")
        # node_by_instance_uuid uses irclient.nodes(); _return_node_to_available
        # re-fetches via get_node.
        client.irclient.nodes.return_value = iter([node])
        client.irclient.get_node.return_value = node

        result = client.release_node_for_router("router-1")

        assert result is node
        (_, target), _ = client.irclient.set_node_provision_state.call_args
        assert target == "deleted"
        _, kwargs = client.irclient.update_node.call_args
        assert kwargs["lessee"] is None
