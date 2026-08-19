"""Tests for openstack_sync.hooks.common — generic shell-operator utilities."""

from __future__ import annotations

import json
import logging
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


def _matching_status(
    *,
    sync_status: str = "Synced",
    message: str = "ok",
    generation: int | None = 1,
) -> dict:
    condition_status = "True" if sync_status == "Synced" else "False"
    reason = "ReconcileSucceeded" if sync_status == "Synced" else "ReconcileFailed"
    status = {
        "syncStatus": sync_status,
        "lastSyncTime": "2026-08-19T06:20:21Z",
        "message": message,
        "conditions": [
            {
                "type": "Synced",
                "status": condition_status,
                "reason": reason,
                "message": message,
                "lastTransitionTime": "2026-08-19T06:20:21Z",
            }
        ],
    }
    if generation is not None:
        status["observedGeneration"] = generation
    return status


def test_status_is_current_ignores_timestamps():
    current = _matching_status(
        message="Successfully reconciled router flavor",
        generation=3,
    )

    assert hc._status_is_current(
        current,
        "Synced",
        "Successfully reconciled router flavor",
        3,
    )


@pytest.mark.parametrize(
    ("current", "sync_status", "message", "generation"),
    [
        (None, "Synced", "ok", 1),
        ({}, "Synced", "ok", 1),
        (_matching_status(sync_status="Failed"), "Synced", "ok", 1),
        (_matching_status(message="old"), "Synced", "new", 1),
        (_matching_status(generation=1), "Synced", "ok", 2),
        ({**_matching_status(), "conditions": []}, "Synced", "ok", 1),
    ],
)
def test_status_is_current_detects_real_status_differences(
    current,
    sync_status,
    message,
    generation,
):
    assert not hc._status_is_current(current, sync_status, message, generation)


# ---------------------------------------------------------------------------
# patch_resource_status
# ---------------------------------------------------------------------------


def test_patch_resource_status_skips_when_disabled():
    with mock.patch("subprocess.run") as mock_run:
        hc.patch_resource_status(
            name="test-flavor",
            namespace="openstack",
            generation=1,
            sync_status="Synced",
            message="ok",
            crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
            crd_kind="NeutronRouterFlavor",
            status_enabled=False,
        )

    mock_run.assert_not_called()


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


def test_patch_resource_status_skips_when_current_status_matches():
    with mock.patch("subprocess.run") as mock_run:
        hc.patch_resource_status(
            name="test-flavor",
            namespace="openstack",
            generation=1,
            sync_status="Synced",
            message="ok",
            crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
            crd_kind="NeutronRouterFlavor",
            status_enabled=True,
            current_status=_matching_status(),
        )

    mock_run.assert_not_called()


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


def test_patch_resource_status_logs_on_kubectl_not_found(caplog):
    with mock.patch("subprocess.run", side_effect=FileNotFoundError):
        with caplog.at_level(logging.WARNING, logger="openstack_sync.hooks.common"):
            hc.patch_resource_status(
                name="test-flavor",
                namespace=None,
                generation=None,
                sync_status="Synced",
                message="ok",
                crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
                crd_kind="NeutronRouterFlavor",
                status_enabled=True,
            )
    assert "kubectl not found" in caplog.text


def test_patch_resource_status_logs_on_kubectl_failure(caplog):
    with mock.patch("subprocess.run") as mock_run:
        mock_run.return_value = mock.MagicMock(
            returncode=1, stderr="not found", stdout=""
        )
        with caplog.at_level(logging.WARNING, logger="openstack_sync.hooks.common"):
            hc.patch_resource_status(
                name="test-flavor",
                namespace="openstack",
                generation=None,
                sync_status="Synced",
                message="ok",
                crd_resource="neutronrouterflavors.neutron.understack.rackspace.net",
                crd_kind="NeutronRouterFlavor",
                status_enabled=True,
            )
    assert "failed to patch" in caplog.text
