from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ironicclient.common.apiclient import exceptions
from tenacity import stop_after_attempt
from tenacity import wait_none

from understack_workflows.ironic.client import IronicClient
from understack_workflows.main import configure_snmpv3_user as cli


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    for name in (
        "get_idle_node",
        "request_transition",
    ):
        policy = getattr(cli, name).retry
        monkeypatch.setattr(policy, "wait", wait_none())
        monkeypatch.setattr(policy, "stop", stop_after_attempt(3))


@pytest.fixture
def client():
    client = Mock(spec=IronicClient)
    node = SimpleNamespace(
        uuid="node-uuid",
        provision_state="manageable",
        target_provision_state=None,
        target_power_state=None,
        reservation=None,
        last_error=None,
        maintenance=False,
        automated_clean=None,
        extra={"existing": "value"},
    )
    client.node = node
    client.get_node.side_effect = lambda _: deepcopy(node)
    client.get_runbook.return_value = SimpleNamespace(
        uuid="runbook-uuid", disable_ramdisk=True, traits=["DELL"]
    )
    client.get_node_traits.return_value = ["DELL"]

    def transition(_, action, **kwargs):
        node.provision_state = {
            "clean": "cleaning",
            "service": "servicing",
        }[action]
        node.target_provision_state = {
            "clean": "manageable",
            "service": "active",
        }.get(action)

    def wait(_, expected):
        node.provision_state = expected
        node.target_provision_state = None

    client.set_node_provision_state.side_effect = transition
    client.wait_for_node_provision_state.side_effect = wait
    return client


@pytest.mark.parametrize(
    ("state", "action"), [("manageable", "clean"), ("active", "service")]
)
def test_runbook_uses_existing_state(client, state, action):
    client.node.provision_state = state

    cli.configure_snmpv3_user(client, "node-uuid")

    client.set_node_provision_state.assert_called_once_with(
        "node-uuid", action, runbook="runbook-uuid"
    )
    client.update_node.assert_not_called()
    assert client.node.provision_state == state


@pytest.mark.parametrize(
    "state",
    ["available", "inspect failed", "enroll", "rescue", "clean failed", "cleaning"],
)
def test_unsupported_states_are_unchanged(client, state):
    client.node.provision_state = state
    with pytest.raises(ValueError, match="expected manageable or active"):
        cli.configure_snmpv3_user(client, "node-uuid")
    client.set_node_provision_state.assert_not_called()
    client.update_node.assert_not_called()


@pytest.mark.parametrize("invalid", ["maintenance", "traits", "ramdisk"])
def test_validation_precedes_state_changes(client, invalid):
    if invalid == "maintenance":
        client.node.maintenance = True
    elif invalid == "traits":
        client.get_node_traits.return_value = []
    else:
        client.get_runbook.return_value.disable_ramdisk = False
    with pytest.raises(
        ValueError, match=r"maintenance|matching trait|disable the ramdisk"
    ):
        cli.configure_snmpv3_user(client, "node-uuid")
    client.set_node_provision_state.assert_not_called()


def test_busy_node_is_read_again_before_any_mutation(client):
    busy = deepcopy(client.node)
    busy.target_power_state = "power on"
    client.get_node.side_effect = [busy, client.node]
    get_idle = cli.get_idle_node.retry_with(  # pyright: ignore[reportFunctionMemberAccess]
        wait=wait_none(), stop=stop_after_attempt(2)
    )
    assert get_idle(client, "node-uuid") is client.node
    assert client.get_node.call_count == 2


def test_main_resolves_node(mocker):
    mocker.patch("sys.argv", ["configure-snmpv3-user", "--node", "Dell-ABC1234"])
    client = mocker.patch.object(cli, "IronicClient").return_value
    client.get_node.return_value.uuid = "node-uuid"
    configure = mocker.patch.object(cli, "configure_snmpv3_user")
    cli.main()
    configure.assert_called_once_with(client, "node-uuid")


@pytest.mark.parametrize(
    ("state", "action"), [("manageable", "clean"), ("active", "service")]
)
def test_conflicting_transition_is_retried(client, state, action):
    client.node.provision_state = state
    transition = client.set_node_provision_state.side_effect
    rejected = False

    def conflict_once(node_uuid, requested, **kwargs):
        nonlocal rejected
        if not rejected:
            rejected = True
            raise exceptions.Conflict("Reserved by another conductor")
        transition(node_uuid, requested, **kwargs)

    client.set_node_provision_state.side_effect = conflict_once
    cli.configure_snmpv3_user(client, "node-uuid")
    actions = [c.args[1] for c in client.set_node_provision_state.call_args_list]
    assert actions == [action, action]


def test_conductor_reservation_blocks_mutation(client):
    client.node.reservation = "conductor"
    with pytest.raises(exceptions.Conflict):
        cli.configure_snmpv3_user(client, "node-uuid")
    client.set_node_provision_state.assert_not_called()


def test_changed_state_is_revalidated_after_conflict(client):
    def conflict_and_change(*args, **kwargs):
        client.node.provision_state = "available"
        raise exceptions.Conflict("Changed concurrently")

    client.set_node_provision_state.side_effect = conflict_and_change
    with pytest.raises(ValueError, match="no longer ready"):
        cli.configure_snmpv3_user(client, "node-uuid")
    assert client.set_node_provision_state.call_count == 1


def test_conflict_retries_are_bounded(client):
    client.set_node_provision_state.side_effect = exceptions.Conflict("Locked")
    with pytest.raises(exceptions.Conflict):
        cli.configure_snmpv3_user(client, "node-uuid")
    assert client.set_node_provision_state.call_count == 3
    client.wait_for_node_provision_state.assert_not_called()


@pytest.mark.parametrize("state", ["manageable", "active"])
def test_runbook_failure_is_reported(client, state):
    client.node.provision_state = state
    wait = client.wait_for_node_provision_state.side_effect

    def complete_with_error(node_uuid, expected):
        if client.node.provision_state in {"cleaning", "servicing"}:
            client.node.last_error = "SNMP credential update failed"
        wait(node_uuid, expected)

    client.wait_for_node_provision_state.side_effect = complete_with_error
    with pytest.raises(RuntimeError, match="SNMP credential update failed"):
        cli.configure_snmpv3_user(client, "node-uuid")
    assert client.node.provision_state == state
