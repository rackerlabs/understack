"""Tests for openstack_sync.hooks.common -- generic shell-operator utilities."""

from __future__ import annotations

import json
import logging
from unittest import mock

import pytest
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


API_VERSION = "neutron.understack.rackspace.net/v1alpha1"
RESOURCE = "neutronrouterflavors.neutron.understack.rackspace.net"


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
    api = mock.MagicMock()
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        hc.patch_resource_status(**kwargs)
    return api.patch_namespaced_custom_object_status


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

    status = kwargs["body"]["status"]
    assert status["syncStatus"] == "Synced"
    assert status["observedGeneration"] == 2
    assert [c["type"] for c in status["conditions"]] == ["Synced"]


def test_patch_resource_status_omits_generation_when_absent():
    status = _patch(generation=None).call_args.kwargs["body"]["status"]
    assert "observedGeneration" not in status


def test_patch_resource_status_skips_when_current_status_matches():
    call = _patch(generation=1, message="ok", current_status=_matching_status())
    assert not call.called


def test_patch_resource_status_skips_without_a_namespace(caplog):
    with caplog.at_level(logging.WARNING, logger="openstack_sync.hooks.common"):
        call = _patch(namespace=None)

    assert not call.called
    assert "no namespace to address it in" in caplog.text


def test_patch_resource_status_skips_on_unusable_crd_identity(caplog):
    with caplog.at_level(logging.WARNING, logger="openstack_sync.hooks.common"):
        call = _patch(crd_api_version="no-version-here")

    assert not call.called
    assert "cannot derive a CRD request target" in caplog.text


def test_patch_resource_status_logs_api_errors(caplog):
    api = mock.MagicMock()
    api.patch_namespaced_custom_object_status.side_effect = ApiException(
        status=403, reason="Forbidden"
    )
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(logging.WARNING, logger="openstack_sync.hooks.common"):
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


# Bodies below are what a real API server sends, read off a live cluster. The
# body is the whole basis for telling a deleted CR from a misconfigured chart.

GROUP = API_VERSION.split("/")[0]
PLURAL = RESOURCE.split(".")[0]

#: A plural, group or version the API server does not serve. Not JSON.
MISSING_RESOURCE_BODY = "404 page not found"


def _status_body(name: str, *, code: int, reason: str, message: str) -> str:
    """Build the Status the API server returns for a named object."""
    return json.dumps(
        {
            "kind": "Status",
            "apiVersion": "v1",
            "metadata": {},
            "status": "Failure",
            "message": message,
            "reason": reason,
            "details": {"name": name, "group": GROUP, "kind": PLURAL},
            "code": code,
        }
    )


def _missing_object(name: str) -> ApiException:
    exc = ApiException(status=404, reason="Not Found")
    exc.body = _status_body(
        name, code=404, reason="NotFound", message=f'{RESOURCE} "{name}" not found'
    )
    return exc


def _forbidden(name: str) -> ApiException:
    """A 403 names the object in ``details.name`` exactly as a 404 does."""
    exc = ApiException(status=403, reason="Forbidden")
    exc.body = _status_body(
        name,
        code=403,
        reason="Forbidden",
        message=f'{RESOURCE} "{name}" is forbidden: User "sa" cannot patch',
    )
    return exc


def _not_found(body: str) -> ApiException:
    exc = ApiException(status=404, reason="Not Found")
    exc.body = body
    return exc


def _patch_status_with(exc: ApiException, name: str = "deleted-flavor") -> None:
    api = mock.MagicMock()
    api.patch_namespaced_custom_object_status.side_effect = exc
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        hc.patch_resource_status(
            name=name,
            namespace="openstack",
            generation=None,
            sync_status="Failed",
            message="OpenStack connection failed",
            crd_api_version=API_VERSION,
            crd_resource=RESOURCE,
            crd_kind="NeutronRouterFlavor",
            status_enabled=True,
        )


def test_patch_resource_status_does_not_error_when_the_cr_is_gone(caplog):
    """A CR deleted mid-reconcile is a race, not a fault worth an error line."""
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.common"):
        _patch_status_with(_missing_object("deleted-flavor"))

    assert "the CR is gone" in caplog.text
    assert "404" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_patch_resource_status_warns_when_the_crd_is_the_thing_missing(caplog):
    """A 404 for the resource, not the object, is a chart misconfiguration.

    It leaves every CR without a status and nothing else reports it, since the
    patch never fails a reconcile.
    """
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.common"):
        _patch_status_with(_not_found(MISSING_RESOURCE_BODY))

    assert "failed to patch" in caplog.text
    assert [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_patch_resource_status_warns_when_denied_for_the_very_same_object(caplog):
    """A 403 names the object just as a 404 does, and is not a deleted CR.

    Matching on the body alone would read an RBAC gap as a race.
    """
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.common"):
        _patch_status_with(_forbidden("deleted-flavor"))

    assert "failed to patch" in caplog.text
    assert "403" in caplog.text


def test_patch_resource_status_warns_when_a_404_names_a_different_object(caplog):
    """The name has to match; a 404 about something else is not this CR's race."""
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.common"):
        _patch_status_with(_missing_object("other-flavor"))

    assert "failed to patch" in caplog.text
    assert [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize(
    ("body", "shape"),
    [
        (
            json.dumps({"kind": "Status", "reason": "NotFound", "code": 404}),
            "no details",
        ),
        (json.dumps({"kind": "Status", "details": None, "code": 404}), "null details"),
        (json.dumps(["not", "a", "status"]), "not an object"),
    ],
)
def test_patch_resource_status_warns_when_a_404_body_names_nothing(body, shape, caplog):
    """A body naming no object cannot clear a CR as gone, and must not raise.

    This runs inside the ApiException handler, where a raise escapes the handler
    below it and fails the reconcile.
    """
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.common"):
        _patch_status_with(_not_found(body))

    assert "failed to patch" in caplog.text, shape
    assert [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_patch_resource_status_logs_unexpected_errors(caplog):
    with mock.patch.object(
        hc, "_customobjects_api", side_effect=RuntimeError("no kubeconfig")
    ):
        with caplog.at_level(logging.WARNING, logger="openstack_sync.hooks.common"):
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
