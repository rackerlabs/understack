"""Tests for openstack_sync.hooks.common -- generic shell-operator utilities."""

from __future__ import annotations

import json
import logging
from unittest import mock

import pytest
from kubernetes import client as k8s_client
from kubernetes.client.exceptions import ApiException

from openstack_sync.hooks import common as hc

# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------


def test_configure_logging_defaults_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    with mock.patch.object(logging, "basicConfig") as basic_config:
        hc.configure_logging()

    assert basic_config.call_args.kwargs["level"] == "INFO"


def test_configure_logging_reads_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "debug")

    with mock.patch.object(logging, "basicConfig") as basic_config:
        hc.configure_logging()

    assert basic_config.call_args.kwargs["level"] == "DEBUG"


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
    condition = {
        "type": "Ready",
        "status": "True" if sync_status == "Synced" else "False",
        "reason": "Reconciled" if sync_status == "Synced" else "ReconcileError",
        "message": message,
        "lastTransitionTime": "2026-08-19T06:20:21Z",
    }
    if generation is not None:
        condition["observedGeneration"] = generation

    status = {
        "syncStatus": sync_status,
        "lastSyncTime": "2026-08-19T06:20:21Z",
        "message": message,
        "conditions": [condition],
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
        (
            {
                **_matching_status(),
                "conditions": [{"type": "Reachable", "status": "True"}],
            },
            "Synced",
            "ok",
            1,
        ),
    ],
)
def test_status_is_current_detects_real_status_differences(
    current,
    sync_status,
    message,
    generation,
):
    assert not hc._status_is_current(current, sync_status, message, generation)


def test_status_is_current_rejects_a_stale_condition_generation():
    current = _matching_status(generation=2)
    current["conditions"][0]["observedGeneration"] = 1

    assert not hc._status_is_current(current, "Synced", "ok", 2)


# ---------------------------------------------------------------------------
# patch_resource_status
# ---------------------------------------------------------------------------


API_VERSION = "neutron.understack.rackspace.net/v1alpha1"
RESOURCE = "neutronrouterflavors.neutron.understack.rackspace.net"


def _fake_api():
    """Return a CustomObjectsApi mock that only accepts real client calls.

    Specced against the real class, because an unspecced mock accepts any method
    name and any signature: a call the client does not have would pass here and
    surface in production only as a logged error.
    """
    return mock.create_autospec(k8s_client.CustomObjectsApi, instance=True)


def _patch(**overrides):
    """Call patch_resource_status against a mocked API, returning the mock."""
    kwargs = {
        "name": "test-flavor",
        "namespace": "openstack",
        "generation": 2,
        "sync_status": "Synced",
        "message": "all good",
        "crd_api_version": API_VERSION,
        "crd_resource": RESOURCE,
        "crd_kind": "NeutronRouterFlavor",
        "status_enabled": True,
    }
    kwargs.update(overrides)
    api = _fake_api()
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        hc.patch_resource_status(**kwargs)
    return api.patch_namespaced_custom_object_status


def _written_condition(**overrides) -> dict:
    """Return the one condition the patch wrote."""
    (condition,) = _patch(**overrides).call_args.kwargs["body"]["status"]["conditions"]
    return condition


def test_patch_resource_status_skips_when_disabled():
    assert not _patch(status_enabled=False).called


def test_patch_resource_status_calls_the_api():
    call = _patch()

    call.assert_called_once()
    kwargs = call.call_args.kwargs
    assert kwargs["group"] == "neutron.understack.rackspace.net"
    assert kwargs["version"] == "v1alpha1"
    assert kwargs["plural"] == "neutronrouterflavors"
    assert kwargs["namespace"] == "openstack"
    assert kwargs["name"] == "test-flavor"
    assert kwargs["_content_type"] == "application/merge-patch+json"

    status = kwargs["body"]["status"]
    assert status["syncStatus"] == "Synced"
    assert status["observedGeneration"] == 2
    assert [c["type"] for c in status["conditions"]] == ["Ready"]


def test_patch_resource_status_writes_the_ready_condition():
    condition = _written_condition()

    assert condition["type"] == "Ready"
    assert condition["status"] == "True"
    assert condition["reason"] == "Reconciled"
    assert condition["message"] == "all good"
    assert condition["observedGeneration"] == 2
    assert condition["lastTransitionTime"].endswith("Z")


def test_patch_resource_status_condition_goes_false_on_failure():
    condition = _written_condition(sync_status="Failed", message="boom")

    assert condition["status"] == "False"
    assert condition["reason"] == "ReconcileError"


def test_patch_resource_status_omits_condition_generation_when_absent():
    assert "observedGeneration" not in _written_condition(generation=None)


def test_patch_resource_status_omits_generation_when_absent():
    status = _patch(generation=None).call_args.kwargs["body"]["status"]
    assert "observedGeneration" not in status


def test_patch_resource_status_keeps_transition_time_when_status_is_unchanged():
    """A message-only change must not restamp lastTransitionTime."""
    condition = _written_condition(
        generation=1,
        message="ok, with more detail",
        current_status=_matching_status(message="ok"),
    )

    assert condition["lastTransitionTime"] == "2026-08-19T06:20:21Z"


def test_patch_resource_status_restamps_transition_time_when_status_flips():
    condition = _written_condition(
        generation=1,
        sync_status="Failed",
        message="boom",
        current_status=_matching_status(message="ok"),
    )

    assert condition["lastTransitionTime"] != "2026-08-19T06:20:21Z"


def test_patch_resource_status_restamps_a_condition_missing_a_transition_time():
    current = _matching_status(message="ok")
    del current["conditions"][0]["lastTransitionTime"]

    condition = _written_condition(
        generation=1, message="changed", current_status=current
    )

    assert condition["lastTransitionTime"].endswith("Z")


def test_patch_resource_status_skips_when_current_status_matches():
    call = _patch(generation=1, message="ok", current_status=_matching_status())
    assert not call.called


def test_patch_resource_status_skips_without_a_namespace(caplog):
    with caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.common"):
        call = _patch(namespace=None)

    assert not call.called
    assert "no namespace to address it in" in caplog.text


def test_patch_resource_status_skips_on_unusable_crd_identity(caplog):
    with caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.common"):
        call = _patch(crd_api_version="no-version-here")

    assert not call.called
    assert "cannot derive a CRD request target" in caplog.text


def test_patch_resource_status_logs_api_errors(caplog):
    api = _fake_api()
    api.patch_namespaced_custom_object_status.side_effect = ApiException(
        status=403, reason="Forbidden"
    )
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.common"):
            hc.patch_resource_status(
                name="test-flavor",
                namespace="openstack",
                generation=None,
                sync_status="Synced",
                message="ok",
                crd_api_version=API_VERSION,
                crd_resource=RESOURCE,
                crd_kind="NeutronRouterFlavor",
                status_enabled=True,
            )

    assert "failed to patch" in caplog.text
    # The point of moving off kubectl: the HTTP status survives into the log.
    assert "403" in caplog.text
    assert "Forbidden" in caplog.text


def test_patch_resource_status_logs_unexpected_errors(caplog):
    with mock.patch.object(
        hc, "_customobjects_api", side_effect=RuntimeError("no kubeconfig")
    ):
        with caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.common"):
            hc.patch_resource_status(
                name="test-flavor",
                namespace="openstack",
                generation=None,
                sync_status="Synced",
                message="ok",
                crd_api_version=API_VERSION,
                crd_resource=RESOURCE,
                crd_kind="NeutronRouterFlavor",
                status_enabled=True,
            )

    assert "failed to patch" in caplog.text
    assert "RuntimeError" in caplog.text


# ---------------------------------------------------------------------------
# crd_request_target
# ---------------------------------------------------------------------------


def test_crd_request_target_splits_the_chart_supplied_values():
    assert hc.crd_request_target(API_VERSION, RESOURCE) == (
        "neutron.understack.rackspace.net",
        "v1alpha1",
        "neutronrouterflavors",
    )


@pytest.mark.parametrize(
    ("api_version", "resource"),
    [
        ("", RESOURCE),
        ("neutron.understack.rackspace.net", RESOURCE),  # no version
        ("/v1alpha1", RESOURCE),  # no group
        (API_VERSION, ""),  # no plural
    ],
)
def test_crd_request_target_rejects_unusable_values(api_version, resource):
    with pytest.raises(ValueError, match="cannot derive a CRD request target"):
        hc.crd_request_target(api_version, resource)


# ---------------------------------------------------------------------------
# _api_error_detail
# ---------------------------------------------------------------------------


def test_api_error_detail_without_a_body():
    exc = ApiException(status=404, reason="Not Found")
    assert hc._api_error_detail(exc) == "HTTP 404 Not Found"


def test_api_error_detail_decodes_the_bytes_body_the_client_supplies():
    exc = ApiException(status=422, reason="Unprocessable Entity")
    exc.body = b'{"kind":"Status",\n "message":"conditions in body is required"}'

    detail = hc._api_error_detail(exc)

    assert "conditions in body is required" in detail
    assert "\\n" not in detail
    assert not detail.startswith("HTTP 422 Unprocessable Entity: b'")


def test_api_error_detail_flattens_and_truncates_the_body():
    exc = ApiException(status=422, reason="Unprocessable Entity")
    exc.body = "line one\n" + "x" * 4000

    detail = hc._api_error_detail(exc)

    assert detail.startswith("HTTP 422 Unprocessable Entity: line one ")
    assert "\n" not in detail
    # The prefix plus a 512-character body at most, so one apiserver Status
    # object cannot flood the log.
    assert len(detail) <= len("HTTP 422 Unprocessable Entity: ") + 512
    assert detail.endswith("...")
