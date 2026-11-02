from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import call

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
        "suppress_cleaning",
        "restore_cleaning_policy",
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

    def update(_, patch):
        for operation in patch:
            path = operation["path"]
            if path == "/automated_clean":
                node.automated_clean = operation["value"]
            elif operation["op"] == "remove":
                del node.extra[path.split("/")[-1]]
            else:
                node.extra[path.split("/")[-1]] = operation["value"]

    def transition(_, action, **kwargs):
        if action == "provide":
            assert node.automated_clean is False
        node.provision_state = {
            "manage": "manageable",
            "clean": "cleaning",
            "service": "servicing",
            "provide": "cleaning",
        }[action]
        node.target_provision_state = {
            "clean": "manageable",
            "service": "active",
            "provide": "available",
        }.get(action)

    def wait(_, expected):
        node.provision_state = expected
        node.target_provision_state = None

    client.update_node.side_effect = update
    client.set_node_provision_state.side_effect = transition
    client.wait_for_node_provision_state.side_effect = wait
    return client


@pytest.mark.parametrize("original", [None, True, False])
def test_available_node_skips_automated_cleaning_and_restores_policy(client, original):
    client.node.provision_state = "available"
    client.node.automated_clean = original

    cli.configure_snmpv3_user(client, "node-uuid")

    assert client.set_node_provision_state.call_args_list == [
        call("node-uuid", "manage"),
        call("node-uuid", "clean", runbook="runbook-uuid"),
        call("node-uuid", "provide"),
    ]
    assert client.node.provision_state == "available"
    assert client.node.automated_clean is original
    assert client.node.extra == {"existing": "value"}


@pytest.mark.parametrize(
    ("state", "action"), [("manageable", "clean"), ("active", "service")]
)
def test_runbook_uses_existing_state_without_changing_cleaning_policy(
    client, state, action
):
    client.node.provision_state = state

    cli.configure_snmpv3_user(client, "node-uuid")

    client.set_node_provision_state.assert_called_once_with(
        "node-uuid", action, runbook="runbook-uuid"
    )
    client.update_node.assert_not_called()
    assert client.node.provision_state == state


@pytest.mark.parametrize(
    "state", ["inspect failed", "enroll", "rescue", "clean failed"]
)
def test_unsupported_states_are_unchanged(client, state):
    client.node.provision_state = state
    with pytest.raises(ValueError, match="Cannot run the SNMP runbook"):
        cli.configure_snmpv3_user(client, "node-uuid")
    client.set_node_provision_state.assert_not_called()
    client.update_node.assert_not_called()


@pytest.mark.parametrize("invalid", ["maintenance", "traits", "ramdisk"])
def test_validation_precedes_policy_and_state_changes(client, invalid):
    client.node.provision_state = "available"
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
    client.update_node.assert_not_called()


def test_cleaning_failure_restores_policy_without_providing(client):
    client.node.provision_state = "available"
    client.node.automated_clean = True
    wait = client.wait_for_node_provision_state.side_effect

    def fail_cleaning(node_uuid, expected):
        if expected == "manageable" and client.node.provision_state == "cleaning":
            client.node.provision_state = "clean failed"
            raise RuntimeError("SNMP failed")
        wait(node_uuid, expected)

    client.wait_for_node_provision_state.side_effect = fail_cleaning
    with pytest.raises(RuntimeError, match="SNMP failed"):
        cli.configure_snmpv3_user(client, "node-uuid")
    assert client.node.automated_clean is True
    assert cli.CLEANING_POLICY_KEY not in client.node.extra
    assert client.node.provision_state == "clean failed"
    assert (
        call("node-uuid", "provide")
        not in client.set_node_provision_state.call_args_list
    )


@pytest.mark.parametrize("target", ["manageable", "available"])
def test_timeout_keeps_suppression_and_saved_policy_until_recovery(client, target):
    client.node.provision_state = "available"
    client.node.automated_clean = True
    wait = client.wait_for_node_provision_state.side_effect

    def timeout(node_uuid, expected):
        if client.node.target_provision_state == target:
            raise TimeoutError("Still cleaning")
        wait(node_uuid, expected)

    client.wait_for_node_provision_state.side_effect = timeout
    with pytest.raises(
        exceptions.Conflict, match="automated cleaning remains disabled"
    ):
        cli.configure_snmpv3_user(client, "node-uuid")
    assert client.node.automated_clean is False
    assert client.node.extra[cli.CLEANING_POLICY_KEY] is True

    client.wait_for_node_provision_state.side_effect = wait
    cli.configure_snmpv3_user(client, "node-uuid")
    assert client.node.provision_state == "available"
    assert client.node.automated_clean is True
    assert cli.CLEANING_POLICY_KEY not in client.node.extra


@pytest.mark.parametrize("state", ["available", "manageable"])
def test_retry_recovers_original_null_policy_after_interruption(client, state):
    client.node.provision_state = state
    client.node.automated_clean = False
    client.node.extra[cli.CLEANING_POLICY_KEY] = None
    cli.configure_snmpv3_user(client, "node-uuid")
    assert client.node.provision_state == "available"
    assert client.node.automated_clean is None
    assert client.node.extra == {"existing": "value"}


def test_provide_rejection_keeps_cleaning_disabled_for_retry(client):
    client.node.provision_state = "available"
    client.node.automated_clean = True
    transition = client.set_node_provision_state.side_effect

    def reject_provide(node_uuid, action, **kwargs):
        if action == "provide":
            raise exceptions.BadRequest("Cannot provide")
        transition(node_uuid, action, **kwargs)

    client.set_node_provision_state.side_effect = reject_provide
    with pytest.raises(
        exceptions.Conflict, match="automated cleaning remains disabled"
    ):
        cli.configure_snmpv3_user(client, "node-uuid")
    assert client.node.automated_clean is False
    assert client.node.extra[cli.CLEANING_POLICY_KEY] is True


def test_policy_restore_failure_keeps_recovery_data(client):
    client.node.provision_state = "available"
    update = client.update_node.side_effect

    def fail_restoration(node_uuid, patch):
        if patch[-1]["op"] == "remove":
            raise exceptions.ServiceUnavailable("Cannot restore policy")
        update(node_uuid, patch)

    client.update_node.side_effect = fail_restoration
    with pytest.raises(exceptions.ServiceUnavailable):
        cli.configure_snmpv3_user(client, "node-uuid")
    assert client.node.automated_clean is False
    assert cli.CLEANING_POLICY_KEY in client.node.extra

    client.update_node.side_effect = update
    cli.configure_snmpv3_user(client, "node-uuid")
    assert client.node.automated_clean is None
    assert cli.CLEANING_POLICY_KEY not in client.node.extra


def test_busy_node_is_read_again_before_any_mutation(client):
    busy = deepcopy(client.node)
    busy.target_power_state = "power on"
    client.get_node.side_effect = [busy, client.node]
    get_idle = cli.get_idle_node.retry_with(  # pyright: ignore[reportFunctionMemberAccess]
        wait=wait_none(), stop=stop_after_attempt(2)
    )
    assert get_idle(client, "node-uuid") is client.node
    assert client.get_node.call_count == 2
    client.update_node.assert_not_called()


def test_main_resolves_node(mocker):
    mocker.patch("sys.argv", ["configure-snmpv3-user", "--node", "Dell-ABC1234"])
    client = mocker.patch.object(cli, "IronicClient").return_value
    client.get_node.return_value.uuid = "node-uuid"
    configure = mocker.patch.object(cli, "configure_snmpv3_user")
    cli.main()
    configure.assert_called_once_with(client, "node-uuid")


@pytest.mark.parametrize("action", ["manage", "clean", "service", "provide"])
def test_conflicting_transition_is_retried_without_repeating_runbook(client, action):
    client.node.provision_state = "active" if action == "service" else "available"
    transition = client.set_node_provision_state.side_effect
    rejected = False

    def conflict_once(node_uuid, requested, **kwargs):
        nonlocal rejected
        if requested == action and not rejected:
            rejected = True
            raise exceptions.Conflict("Reserved by another conductor")
        transition(node_uuid, requested, **kwargs)

    client.set_node_provision_state.side_effect = conflict_once
    cli.configure_snmpv3_user(client, "node-uuid")
    actions = [c.args[1] for c in client.set_node_provision_state.call_args_list]
    assert actions.count(action) == 2
    if action not in {"clean", "service"}:
        assert actions.count("clean") == 1


@pytest.mark.parametrize("restoring", [True, False])
def test_conflicting_policy_update_is_retried(client, restoring):
    client.node.provision_state = "available"
    client.node.automated_clean = True
    update = client.update_node.side_effect
    rejected = False

    def conflict_once(node_uuid, patch):
        nonlocal rejected
        if (patch[-1]["op"] == "remove") == restoring and not rejected:
            rejected = True
            raise exceptions.Conflict("Locked")
        update(node_uuid, patch)

    client.update_node.side_effect = conflict_once
    cli.configure_snmpv3_user(client, "node-uuid")
    assert client.update_node.call_count == 3
    assert client.node.automated_clean is True
    assert cli.CLEANING_POLICY_KEY not in client.node.extra


def test_conductor_reservation_blocks_mutation(client):
    client.node.reservation = "conductor"
    with pytest.raises(exceptions.Conflict):
        cli.configure_snmpv3_user(client, "node-uuid")
    client.set_node_provision_state.assert_not_called()


def test_changed_state_is_revalidated_after_conflict(client):
    def conflict_and_change(*args, **kwargs):
        client.node.provision_state = "active"
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


@pytest.mark.parametrize("state", ["available", "manageable", "active"])
def test_runbook_failure_is_reported_even_when_state_is_restored(client, state):
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
    assert client.node.automated_clean is None
    assert cli.CLEANING_POLICY_KEY not in client.node.extra
