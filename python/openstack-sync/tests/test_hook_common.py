"""Tests for openstack_sync.hooks.common — generic shell-operator utilities."""

from __future__ import annotations

import json
from unittest import mock

import pytest

from openstack_sync.hooks import common as hc

# ---------------------------------------------------------------------------
# Type coercions
# ---------------------------------------------------------------------------


def test_string_or_none_returns_none_for_none():
    assert hc.string_or_none(None) is None


def test_string_or_none_converts_value():
    assert hc.string_or_none(42) == "42"
    assert hc.string_or_none("hello") == "hello"


def test_int_or_none_returns_none_for_none():
    assert hc.int_or_none(None) is None


def test_int_or_none_converts_int_string():
    assert hc.int_or_none("7") == 7
    assert hc.int_or_none(3) == 3


def test_int_or_none_returns_none_for_invalid():
    assert hc.int_or_none("not-a-number") is None
    assert hc.int_or_none([]) is None


# ---------------------------------------------------------------------------
# read_binding_context
# ---------------------------------------------------------------------------


def test_read_binding_context_returns_empty_when_no_env(monkeypatch):
    monkeypatch.delenv("BINDING_CONTEXT_PATH", raising=False)
    assert hc.read_binding_context() == []


def test_read_binding_context_parses_json(monkeypatch, tmp_path):
    ctx = [{"binding": "test", "type": "Event"}]
    ctx_file = tmp_path / "ctx.json"
    ctx_file.write_text(json.dumps(ctx), encoding="utf-8")
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    assert hc.read_binding_context() == ctx


def test_read_binding_context_raises_on_non_list(monkeypatch, tmp_path):
    ctx_file = tmp_path / "ctx.json"
    ctx_file.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with pytest.raises(ValueError, match="must be a list"):
        hc.read_binding_context()


# ---------------------------------------------------------------------------
# snapshot_items
# ---------------------------------------------------------------------------


def test_snapshot_items_returns_items():
    contexts = [
        {
            "binding": "schedule",
            "snapshots": {"my-binding": [{"object": {"id": "1"}}]},
        }
    ]
    items = hc.snapshot_items(contexts, "my-binding")
    assert items == [{"object": {"id": "1"}}]


def test_snapshot_items_returns_none_when_absent():
    contexts = [{"binding": "schedule", "snapshots": {"other": []}}]
    assert hc.snapshot_items(contexts, "my-binding") is None


def test_snapshot_items_raises_on_non_list():
    contexts = [{"snapshots": {"my-binding": "not-a-list"}}]
    with pytest.raises(ValueError, match="must be a list"):
        hc.snapshot_items(contexts, "my-binding")


# ---------------------------------------------------------------------------
# synchronization_items
# ---------------------------------------------------------------------------


def test_synchronization_items_returns_objects():
    contexts = [
        {
            "binding": "my-binding",
            "type": "Synchronization",
            "objects": [{"object": {"id": "1"}}],
        }
    ]
    items = hc.synchronization_items(contexts, "my-binding")
    assert items == [{"object": {"id": "1"}}]


def test_synchronization_items_returns_none_when_absent():
    contexts = [{"binding": "other", "type": "Synchronization", "objects": []}]
    assert hc.synchronization_items(contexts, "my-binding") is None


def test_synchronization_items_raises_on_non_list():
    contexts = [{"binding": "my-binding", "type": "Synchronization", "objects": "bad"}]
    with pytest.raises(ValueError, match="must be a list"):
        hc.synchronization_items(contexts, "my-binding")


# ---------------------------------------------------------------------------
# utc_timestamp / truncate_message
# ---------------------------------------------------------------------------


def test_utc_timestamp_format():
    ts = hc.utc_timestamp()
    assert ts.endswith("Z")
    assert "T" in ts


def test_truncate_message_short():
    assert hc.truncate_message("hello") == "hello"


def test_truncate_message_exact_limit():
    msg = "x" * 2048
    assert hc.truncate_message(msg) == msg


def test_truncate_message_truncates():
    msg = "x" * 3000
    result = hc.truncate_message(msg)
    assert len(result) == 2048
    assert result.endswith("...")


def test_truncate_message_custom_limit():
    result = hc.truncate_message("abcdefgh", max_length=5)
    assert result == "ab..."


# ---------------------------------------------------------------------------
# patch_resource_status
# ---------------------------------------------------------------------------


def test_patch_resource_status_skips_when_disabled():
    logs = []
    hc.patch_resource_status(
        name="test-flavor",
        namespace="openstack",
        generation=1,
        sync_status="Synced",
        message="ok",
        crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
        crd_kind="NeutronRouterFlavor",
        status_enabled=False,
        log_fn=logs.append,
    )
    assert logs == []


def test_patch_resource_status_calls_kubectl():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(returncode=0)
        hc.patch_resource_status(
            name="test-flavor",
            namespace="openstack",
            generation=2,
            sync_status="Synced",
            message="all good",
            crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
            crd_kind="NeutronRouterFlavor",
            status_enabled=True,
        )

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "kubectl" in cmd
    assert "test-flavor" in cmd
    assert "-n" in cmd
    assert "openstack" in cmd


def test_patch_resource_status_no_namespace():
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(returncode=0)
        hc.patch_resource_status(
            name="test-flavor",
            namespace=None,
            generation=None,
            sync_status="Failed",
            message="error",
            crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
            crd_kind="NeutronRouterFlavor",
            status_enabled=True,
        )

    cmd = mock_run.call_args[0][0]
    assert "-n" not in cmd


def test_patch_resource_status_logs_on_kubectl_not_found():
    logs = []
    with mock.patch("subprocess.run", side_effect=FileNotFoundError):
        hc.patch_resource_status(
            name="test-flavor",
            namespace=None,
            generation=None,
            sync_status="Synced",
            message="ok",
            crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
            crd_kind="NeutronRouterFlavor",
            status_enabled=True,
            log_fn=logs.append,
        )
    assert any("kubectl not found" in msg for msg in logs)


def test_patch_resource_status_logs_on_kubectl_failure():
    logs = []
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(
            returncode=1, stderr="not found", stdout=""
        )
        hc.patch_resource_status(
            name="test-flavor",
            namespace="openstack",
            generation=None,
            sync_status="Synced",
            message="ok",
            crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
            crd_kind="NeutronRouterFlavor",
            status_enabled=True,
            log_fn=logs.append,
        )
    assert any("failed to patch" in msg for msg in logs)


# ---------------------------------------------------------------------------
# dispatch_binding_contexts
# ---------------------------------------------------------------------------


def _make_event(binding: str, event_type: str, watch_event: str = "Added") -> dict:
    return {
        "binding": binding,
        "type": event_type,
        "watchEvent": watch_event,
        "object": {"metadata": {"name": "obj-1"}, "spec": {}},
    }


def test_dispatch_synchronization():
    called = []
    contexts = [
        {
            "binding": "my-binding",
            "type": "Synchronization",
            "objects": [
                {"object": {"metadata": {"name": "a"}, "spec": {}}},
                {"object": {"metadata": {"name": "b"}, "spec": {}}},
            ],
        }
    ]
    result = hc.dispatch_binding_contexts(
        contexts, "my-binding", lambda item: called.append(item)
    )
    assert result == 0
    assert len(called) == 2


def test_dispatch_event_added():
    called = []
    contexts = [_make_event("my-binding", "Event", "Added")]
    result = hc.dispatch_binding_contexts(
        contexts, "my-binding", lambda item: called.append(item)
    )
    assert result == 0
    assert len(called) == 1


def test_dispatch_event_deleted_is_skipped():
    called = []
    contexts = [_make_event("my-binding", "Event", "Deleted")]
    result = hc.dispatch_binding_contexts(
        contexts, "my-binding", lambda item: called.append(item)
    )
    assert result == 0
    assert called == []


def test_dispatch_schedule_snapshot():
    called = []
    contexts = [
        {
            "binding": "my-binding",
            "type": "Schedule",
            "snapshots": {
                "my-binding": [
                    {"object": {"metadata": {"name": "x"}, "spec": {}}},
                ]
            },
        }
    ]
    result = hc.dispatch_binding_contexts(
        contexts, "my-binding", lambda item: called.append(item)
    )
    assert result == 0
    assert len(called) == 1


def test_dispatch_ignores_other_bindings():
    called = []
    contexts = [_make_event("other-binding", "Event", "Added")]
    result = hc.dispatch_binding_contexts(
        contexts, "my-binding", lambda item: called.append(item)
    )
    assert result == 0
    assert called == []


def test_dispatch_returns_1_on_reconcile_error():
    logs = []
    contexts = [_make_event("my-binding", "Event", "Added")]
    result = hc.dispatch_binding_contexts(
        contexts,
        "my-binding",
        lambda item: (_ for _ in ()).throw(RuntimeError("boom")),
        log_fn=logs.append,
    )
    assert result == 1
    assert any("reconcile failed" in msg for msg in logs)
