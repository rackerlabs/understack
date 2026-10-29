import argparse
from types import SimpleNamespace
from typing import cast
from unittest.mock import call

import pytest
from ironicclient.v1.node import Node

from understack_workflows import ironic_node
from understack_workflows.main import apply_node_runbook

# --- ironic_node.run_runbook_standalone (state bracketing) -------------------


def _patch_client(
    mocker,
    *,
    provision_state,
    runbook_traits=("CUSTOM_DELL",),
    node_traits=("CUSTOM_DELL",),
):
    client = mocker.patch.object(ironic_node, "IronicClient").return_value
    client.get_runbook.return_value = SimpleNamespace(
        uuid="runbook-123", traits=list(runbook_traits), disable_ramdisk=True
    )
    client.get_node_traits.return_value = list(node_traits)
    mocker.patch.object(
        ironic_node,
        "refresh",
        side_effect=[SimpleNamespace(uuid="node-123", provision_state=provision_state)]
        + [
            SimpleNamespace(
                uuid="node-123",
                provision_state="active"
                if provision_state == "active"
                else "manageable",
            )
        ]
        * 10,
    )
    return client


def test_standalone_available_node_is_bracketed_manage_and_provide(mocker):
    client = _patch_client(mocker, provision_state="available")
    node = cast(Node, SimpleNamespace(uuid="node-123"))

    ironic_node.run_runbook_standalone(node, "bmc-configure-snmpv3-user")

    # manage -> clean(runbook) -> provide, in that order.
    assert client.set_node_provision_state.mock_calls == [
        call(
            "node-123", "manage", clean_steps=None, runbook=None, disable_ramdisk=None
        ),
        call(
            "node-123",
            "clean",
            clean_steps=None,
            runbook="runbook-123",
            disable_ramdisk=None,
        ),
        call(
            "node-123", "provide", clean_steps=None, runbook=None, disable_ramdisk=None
        ),
    ]
    assert client.wait_for_node_provision_state.mock_calls == [
        call("node-123", "manageable", timeout=ironic_node.NODE_STATE_TIMEOUT_SECS),
        call("node-123", "manageable", timeout=ironic_node.NODE_STATE_TIMEOUT_SECS),
        call("node-123", "available", timeout=ironic_node.NODE_STATE_TIMEOUT_SECS),
    ]


def test_standalone_manageable_node_is_not_provided(mocker):
    client = _patch_client(mocker, provision_state="manageable")
    node = cast(Node, SimpleNamespace(uuid="node-123"))

    ironic_node.run_runbook_standalone(node, "bmc-configure-snmpv3-user")

    # No manage, no provide: only the clean runs; node stays manageable.
    assert client.set_node_provision_state.mock_calls == [
        call(
            "node-123",
            "clean",
            clean_steps=None,
            runbook="runbook-123",
            disable_ramdisk=None,
        ),
    ]


def test_standalone_active_node_uses_service_and_waits_for_active(mocker):
    client = _patch_client(mocker, provision_state="active")
    node = cast(Node, SimpleNamespace(uuid="node-123"))

    ironic_node.run_runbook_standalone(node, "bmc-configure-snmpv3-user")

    client.set_node_provision_state.assert_called_once_with(
        "node-123",
        "service",
        clean_steps=None,
        runbook="runbook-123",
        disable_ramdisk=None,
    )
    client.wait_for_node_provision_state.assert_called_once_with(
        "node-123", "active", timeout=ironic_node.NODE_STATE_TIMEOUT_SECS
    )


def test_active_node_allows_existing_instance_and_allocation(mocker):
    client = _patch_client(mocker, provision_state="active")
    node = cast(
        Node,
        SimpleNamespace(
            uuid="node-123",
            provision_state="active",
            instance_uuid="instance-123",
            allocation_id="allocation-123",
        ),
    )
    mocker.patch.object(ironic_node, "refresh", return_value=node)

    ironic_node.run_runbooks_standalone(node, ["first", "second"])

    assert [c.args[1] for c in client.set_node_provision_state.call_args_list] == [
        "service",
        "service",
    ]
    assert client.wait_for_node_provision_state.mock_calls == [
        call("node-123", "active", timeout=ironic_node.NODE_STATE_TIMEOUT_SECS),
        call("node-123", "active", timeout=ironic_node.NODE_STATE_TIMEOUT_SECS),
    ]


@pytest.mark.parametrize("disable_ramdisk", [False, None])
def test_active_sequence_preflights_ramdisk_setting_before_service(
    mocker, disable_ramdisk
):
    client = _patch_client(mocker, provision_state="active")
    client.get_runbook.side_effect = [
        SimpleNamespace(uuid="r-1", traits=["CUSTOM_DELL"], disable_ramdisk=True),
        SimpleNamespace(
            uuid="r-2", traits=["CUSTOM_DELL"], disable_ramdisk=disable_ramdisk
        ),
    ]
    with pytest.raises(ValueError, match="disable_ramdisk=True"):
        ironic_node.run_runbooks_standalone(
            cast(Node, SimpleNamespace(uuid="node-123")), ["first", "second"]
        )
    client.set_node_provision_state.assert_not_called()


def test_active_sequence_stops_on_service_failure_without_state_restoration(mocker):
    client = _patch_client(mocker, provision_state="active")
    client.wait_for_node_provision_state.side_effect = RuntimeError("service failed")
    with pytest.raises(RuntimeError, match="service failed"):
        ironic_node.run_runbooks_standalone(
            cast(Node, SimpleNamespace(uuid="node-123")), ["first", "second"]
        )
    assert [c.args[1] for c in client.set_node_provision_state.call_args_list] == [
        "service"
    ]


def test_active_sequence_refuses_state_change_to_idle_before_service(mocker):
    client = _patch_client(mocker, provision_state="active")
    mocker.patch.object(
        ironic_node,
        "refresh",
        side_effect=[
            SimpleNamespace(uuid="node-123", provision_state=state)
            for state in ["active", "available"]
        ],
    )
    with pytest.raises(ValueError, match="Expected active"):
        ironic_node.run_runbooks_standalone(
            cast(Node, SimpleNamespace(uuid="node-123")), ["first"]
        )
    client.set_node_provision_state.assert_not_called()


def test_standalone_unexpected_state_is_refused(mocker):
    client = _patch_client(mocker, provision_state="deploying")
    node = cast(Node, SimpleNamespace(uuid="node-123"))

    with pytest.raises(ValueError, match="refusing to run runbook"):
        ironic_node.run_runbook_standalone(node, "bmc-configure-snmpv3-user")

    client.set_node_provision_state.assert_not_called()


@pytest.mark.parametrize("runbook_traits", [[], ["CUSTOM_OTHER"], None])
def test_standalone_rejects_ineligible_runbook(mocker, runbook_traits):
    client = _patch_client(
        mocker,
        provision_state="manageable",
        node_traits=("CUSTOM_DELL",),
    )
    client.get_runbook.return_value.traits = runbook_traits
    node = cast(Node, SimpleNamespace(uuid="node-123"))

    with pytest.raises(ValueError, match=r"traits metadata|matching node trait"):
        ironic_node.run_runbook_standalone(node, "bmc-configure-snmpv3-user")

    client.set_node_provision_state.assert_not_called()


# --- CLI ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "value", ["invalid", '"first"', "{}", "null", "[null]", "[1]", '[""]', '[" "]']
)
def test_parse_runbooks_rejects_invalid(value):
    with pytest.raises(argparse.ArgumentTypeError, match="JSON array"):
        apply_node_runbook.parse_runbooks(value)


def test_main_single_node(mocker):
    mocker.patch(
        "sys.argv",
        [
            "apply-node-runbook",
            "--node",
            "node-123",
            "--runbooks",
            '["first", "second"]',
        ],
    )
    mocker.patch.object(apply_node_runbook.helpers, "setup_logger")
    client = mocker.patch.object(apply_node_runbook, "IronicClient").return_value
    run = mocker.patch.object(ironic_node, "run_runbooks_standalone")

    apply_node_runbook.main()

    client.get_node.assert_called_once_with("node-123")
    run.assert_called_once_with(client.get_node.return_value, ["first", "second"])


def test_main_propagates_runbook_failure(mocker):
    mocker.patch(
        "sys.argv",
        ["apply-node-runbook", "--node", "node-123", "--runbooks", '["first"]'],
    )
    mocker.patch.object(apply_node_runbook.helpers, "setup_logger")
    mocker.patch.object(apply_node_runbook, "IronicClient")
    mocker.patch.object(
        ironic_node, "run_runbooks_standalone", side_effect=RuntimeError("clean failed")
    )

    with pytest.raises(RuntimeError, match="clean failed"):
        apply_node_runbook.main()


def test_main_requires_node(mocker, capsys):
    mocker.patch("sys.argv", ["apply-node-runbook", "--runbooks", '["first"]'])
    mocker.patch.object(apply_node_runbook.helpers, "setup_logger")
    client = mocker.patch.object(apply_node_runbook, "IronicClient")

    with pytest.raises(SystemExit) as exc:
        apply_node_runbook.main()

    assert exc.value.code == 2
    assert "--node" in capsys.readouterr().err
    client.assert_not_called()


@pytest.mark.parametrize(
    ("state", "field"),
    [
        (state, field)
        for state in ["available", "manageable", "active"]
        for field in [
            "maintenance",
            "allocation_id",
            "instance_uuid",
            "reservation",
            "target_provision_state",
        ]
        if state != "active" or field not in {"instance_uuid", "allocation_id"}
    ],
)
def test_standalone_refuses_reserved_or_unhealthy_node(mocker, field, state):
    client = _patch_client(mocker, provision_state=state)
    mocker.patch.object(
        ironic_node,
        "refresh",
        return_value=SimpleNamespace(
            uuid="node-123", provision_state=state, **{field: True}
        ),
    )
    with pytest.raises(ValueError, match=field):
        ironic_node.run_runbooks_standalone(
            cast(Node, SimpleNamespace(uuid="node-123")), ["first"]
        )
    client.set_node_provision_state.assert_not_called()


def test_sequence_brackets_once_and_stops_without_provide_on_failure(mocker):
    client = _patch_client(mocker, provision_state="available")
    client.wait_for_node_provision_state.side_effect = [
        None,
        None,
        RuntimeError("clean failed"),
    ]
    node = cast(Node, SimpleNamespace(uuid="node-123"))
    with pytest.raises(RuntimeError, match="clean failed"):
        ironic_node.run_runbooks_standalone(node, ["first", "second", "third"])
    assert [c.args[1] for c in client.set_node_provision_state.call_args_list] == [
        "manage",
        "clean",
        "clean",
    ]


def test_sequence_restores_available_only_once(mocker):
    client = _patch_client(mocker, provision_state="available")
    ironic_node.run_runbooks_standalone(
        cast(Node, SimpleNamespace(uuid="node-123")), ["first", "second"]
    )
    assert [c.args[1] for c in client.set_node_provision_state.call_args_list] == [
        "manage",
        "clean",
        "clean",
        "provide",
    ]


def test_empty_sequence_does_not_change_state(mocker):
    refresh = mocker.patch.object(ironic_node, "refresh")
    ironic_node.run_runbooks_standalone(
        cast(Node, SimpleNamespace(uuid="node-123")), []
    )
    refresh.assert_not_called()


def test_sequence_preflights_later_runbooks_before_state_change(mocker):
    client = _patch_client(mocker, provision_state="available")
    client.get_runbook.side_effect = [
        SimpleNamespace(uuid="r-1", traits=["CUSTOM_DELL"]),
        SimpleNamespace(uuid="r-2", traits=["CUSTOM_OTHER"]),
    ]
    with pytest.raises(ValueError, match="matching node trait"):
        ironic_node.run_runbooks_standalone(
            cast(Node, SimpleNamespace(uuid="node-123")), ["first", "second"]
        )
    client.set_node_provision_state.assert_not_called()


def test_sequence_does_not_provide_when_manage_fails(mocker):
    client = _patch_client(mocker, provision_state="available")
    client.wait_for_node_provision_state.side_effect = RuntimeError("manage failed")
    with pytest.raises(RuntimeError, match="manage failed"):
        ironic_node.run_runbooks_standalone(
            cast(Node, SimpleNamespace(uuid="node-123")), ["first", "second"]
        )
    assert [c.args[1] for c in client.set_node_provision_state.call_args_list] == [
        "manage"
    ]
