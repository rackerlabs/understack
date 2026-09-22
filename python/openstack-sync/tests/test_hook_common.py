"""Tests for framework common shell-operator utilities."""

from __future__ import annotations

import json
import logging
from unittest import mock

import pytest
from kubernetes import client as k8s_client
from kubernetes.client.exceptions import ApiException

from openstack_sync.hooks.framework import common as hc

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
    reason: str | None = None,
) -> dict:
    default_reason = "Reconciled" if sync_status == "Synced" else "ReconcileError"
    condition = {
        "type": "Ready",
        "status": "True" if sync_status == "Synced" else "False",
        "reason": reason or default_reason,
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


def test_status_is_current_matches_when_the_reason_matches():
    current = _matching_status(sync_status="Failed", reason="NautobotPrefixMissing")

    assert hc._status_is_current(
        current, "Failed", "ok", 1, None, "NautobotPrefixMissing"
    )


def test_status_is_current_detects_a_changed_reason():
    """A new reason must not be skipped as a no-op because the message matches."""
    current = _matching_status(sync_status="Failed", reason="ReconcileError")

    assert not hc._status_is_current(
        current, "Failed", "ok", 1, None, "NautobotPrefixMissing"
    )


def test_status_is_current_detects_reason_cleared():
    """Clearing a reason is also a real change, not a no-op."""
    current = _matching_status(sync_status="Failed", reason="NautobotPrefixMissing")

    assert not hc._status_is_current(current, "Failed", "ok", 1, None, None)


def test_status_is_current_rejects_a_stale_condition_generation():
    current = _matching_status(generation=2)
    current["conditions"][0]["observedGeneration"] = 1

    assert not hc._status_is_current(current, "Synced", "ok", 2)


# ---------------------------------------------------------------------------
# _status_is_current: extra_status (plugin-supplied structured status)
# ---------------------------------------------------------------------------


def test_status_is_current_ignores_extra_status_when_not_given():
    """A plugin with no extra_status compares only the framework's own fields."""
    current = _matching_status()
    assert hc._status_is_current(current, "Synced", "ok", 1)
    assert hc._status_is_current(current, "Synced", "ok", 1, None)
    assert hc._status_is_current(current, "Synced", "ok", 1, {})


def test_status_is_current_true_when_extra_status_already_matches():
    current = {**_matching_status(), "prefixes": [{"id": "a", "cidr": "10.0.0.0/8"}]}

    assert hc._status_is_current(
        current, "Synced", "ok", 1, {"prefixes": [{"id": "a", "cidr": "10.0.0.0/8"}]}
    )


def test_status_is_current_false_when_extra_status_value_differs():
    current = {**_matching_status(), "prefixes": [{"id": "a", "cidr": "10.0.0.0/8"}]}

    assert not hc._status_is_current(
        current, "Synced", "ok", 1, {"prefixes": [{"id": "b", "cidr": "10.0.0.0/8"}]}
    )


def test_status_is_current_false_when_extra_status_key_is_missing():
    """A CRD/plugin upgrade that adds a new status field must force a repatch.

    A CR whose status predates the field looks like it lacks 'prefixes'
    entirely; that must count as a mismatch, not as "nothing to compare."
    """
    current = _matching_status()
    assert "prefixes" not in current

    assert not hc._status_is_current(
        current, "Synced", "ok", 1, {"prefixes": [{"id": "a"}]}
    )


def test_status_is_current_true_when_extra_status_value_is_empty_list():
    """An explicit empty list is a real value and must compare, not short-circuit."""
    current = {**_matching_status(), "prefixes": []}

    assert hc._status_is_current(current, "Synced", "ok", 1, {"prefixes": []})


# ---------------------------------------------------------------------------
# patch_resource_status
# ---------------------------------------------------------------------------


API_VERSION = "neutron.understack.rackspace.net/v1alpha1"
RESOURCE = "neutronrouterflavors.neutron.understack.rackspace.net"
FINALIZER = "openstack-sync.understack.rackspace.net/finalizer"
PLURAL = RESOURCE.split(".")[0]
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
            "details": {
                "name": name,
                "group": API_VERSION.partition("/")[0],
                "kind": "neutronrouterflavors",
            },
            "code": code,
        }
    )


def _missing_object(name: str) -> ApiException:
    exc = ApiException(status=404, reason="Not Found")
    exc.body = _status_body(
        name, code=404, reason="NotFound", message=f'{PLURAL} "{name}" not found'
    )
    return exc


def _forbidden(name: str) -> ApiException:
    """A 403 names the object in ``details.name`` exactly as a 404 does."""
    exc = ApiException(status=403, reason="Forbidden")
    exc.body = _status_body(
        name,
        code=403,
        reason="Forbidden",
        message=f'{PLURAL} "{name}" is forbidden',
    )
    return exc


def _not_found(body: str) -> ApiException:
    exc = ApiException(status=404, reason="Not Found")
    exc.body = body
    return exc


def _target(**overrides):
    kwargs = {
        "name": "test-flavor",
        "namespace": "openstack",
        "api_version": API_VERSION,
        "resource": RESOURCE,
        "kind": "NeutronRouterFlavor",
    }
    kwargs.update(overrides)
    return hc.CustomResourceTarget(**kwargs)


def _fake_api():
    """Return a CustomObjectsApi mock that only accepts real client calls.

    Specced against the real class, because an unspecced mock accepts any method
    name and any signature: a call the client does not have would pass here and
    surface in production only as a logged error.
    """
    return mock.create_autospec(k8s_client.CustomObjectsApi, instance=True)


def _add_finalizer(**overrides):
    kwargs = {
        "target": _target(),
        "finalizer": FINALIZER,
        "current_finalizers": [],
    }
    kwargs.update(overrides)
    api = _fake_api()
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        ok = hc.add_resource_finalizer(**kwargs)
    return ok, api.patch_namespaced_custom_object


def _remove_finalizer(**overrides):
    kwargs = {
        "target": _target(),
        "finalizer": FINALIZER,
        "current_finalizers": [FINALIZER],
    }
    kwargs.update(overrides)
    api = _fake_api()
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        ok = hc.remove_resource_finalizer(**kwargs)
    return ok, api.patch_namespaced_custom_object


def test_add_resource_finalizer_creates_finalizer_list():
    ok, call = _add_finalizer(resource_version="12345")

    assert ok is True
    call.assert_called_once()
    kwargs = call.call_args.kwargs
    assert kwargs["group"] == "neutron.understack.rackspace.net"
    assert kwargs["version"] == "v1alpha1"
    assert kwargs["plural"] == "neutronrouterflavors"
    assert kwargs["namespace"] == "openstack"
    assert kwargs["name"] == "test-flavor"
    assert kwargs["_content_type"] == "application/json-patch+json"
    assert kwargs["body"] == [
        {"op": "test", "path": "/metadata/resourceVersion", "value": "12345"},
        {"op": "add", "path": "/metadata/finalizers", "value": [FINALIZER]},
    ]


def test_add_resource_finalizer_appends_without_replacing_existing_finalizers():
    ok, call = _add_finalizer(
        current_finalizers=["example.com/other"], resource_version="12345"
    )

    assert ok is True
    assert call.call_args.kwargs["body"] == [
        {"op": "test", "path": "/metadata/resourceVersion", "value": "12345"},
        {"op": "add", "path": "/metadata/finalizers/-", "value": FINALIZER},
    ]


def test_add_resource_finalizer_skips_when_already_present():
    ok, call = _add_finalizer(current_finalizers=[FINALIZER])

    assert ok is True
    call.assert_not_called()


def test_add_resource_finalizer_requires_resource_version_before_patching(caplog):
    api = _fake_api()
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.ERROR, logger="openstack_sync.hooks.framework.common"
        ):
            ok = hc.add_resource_finalizer(
                target=_target(),
                finalizer=FINALIZER,
                current_finalizers=[],
            )

    assert ok is False
    api.patch_namespaced_custom_object.assert_not_called()
    assert "metadata.resourceVersion is missing" in caplog.text


def test_remove_resource_finalizer_tests_then_removes_the_known_index():
    ok, call = _remove_finalizer(current_finalizers=["example.com/other", FINALIZER])

    assert ok is True
    assert call.call_args.kwargs["body"] == [
        {"op": "test", "path": "/metadata/finalizers/1", "value": FINALIZER},
        {"op": "remove", "path": "/metadata/finalizers/1"},
    ]


def test_remove_resource_finalizer_skips_when_absent():
    ok, call = _remove_finalizer(current_finalizers=["example.com/other"])

    assert ok is True
    call.assert_not_called()


def test_finalizer_patch_failure_is_reported_to_the_caller(caplog):
    api = _fake_api()
    api.patch_namespaced_custom_object.side_effect = ApiException(
        status=409, reason="Conflict"
    )
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.ERROR, logger="openstack_sync.hooks.framework.common"
        ):
            ok = hc.add_resource_finalizer(
                target=_target(),
                finalizer=FINALIZER,
                current_finalizers=[],
                resource_version="12345",
            )

    assert ok is False
    assert "failed to add finalizer" in caplog.text
    assert "409" in caplog.text


def test_add_finalizer_patch_failure_succeeds_when_live_object_already_has_it(caplog):
    api = _fake_api()
    api.patch_namespaced_custom_object.side_effect = ApiException(
        status=422, reason="Unprocessable Entity"
    )
    api.get_namespaced_custom_object.return_value = {
        "metadata": {"finalizers": [FINALIZER]}
    }

    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.INFO, logger="openstack_sync.hooks.framework.common"
        ):
            ok = hc.add_resource_finalizer(
                target=_target(),
                finalizer=FINALIZER,
                current_finalizers=[],
                resource_version="12345",
            )

    assert ok is True
    api.get_namespaced_custom_object.assert_called_once()
    assert "desired finalizer state" in caplog.text
    assert "failed to add finalizer" not in caplog.text


def test_add_finalizer_patch_failure_fails_when_live_object_is_missing(caplog):
    api = _fake_api()
    api.patch_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    api.get_namespaced_custom_object.side_effect = _missing_object("test-flavor")

    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.ERROR, logger="openstack_sync.hooks.framework.common"
        ):
            ok = hc.add_resource_finalizer(
                target=_target(),
                finalizer=FINALIZER,
                current_finalizers=[],
                resource_version="12345",
            )

    assert ok is False
    api.get_namespaced_custom_object.assert_called_once()
    assert "failed to add finalizer" in caplog.text
    assert "404" in caplog.text


def test_remove_finalizer_patch_failure_succeeds_when_live_object_lacks_it(caplog):
    api = _fake_api()
    api.patch_namespaced_custom_object.side_effect = ApiException(
        status=422, reason="Unprocessable Entity"
    )
    api.get_namespaced_custom_object.return_value = {"metadata": {"finalizers": []}}

    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.INFO, logger="openstack_sync.hooks.framework.common"
        ):
            ok = hc.remove_resource_finalizer(
                target=_target(),
                finalizer=FINALIZER,
                current_finalizers=[FINALIZER],
            )

    assert ok is True
    api.get_namespaced_custom_object.assert_called_once()
    assert "desired finalizer state" in caplog.text
    assert "failed to remove finalizer" not in caplog.text


def test_remove_finalizer_patch_failure_fails_when_live_object_is_missing(caplog):
    api = _fake_api()
    api.patch_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    api.get_namespaced_custom_object.side_effect = _missing_object("test-flavor")

    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.ERROR, logger="openstack_sync.hooks.framework.common"
        ):
            ok = hc.remove_resource_finalizer(
                target=_target(),
                finalizer=FINALIZER,
                current_finalizers=[FINALIZER],
            )

    assert ok is False
    api.get_namespaced_custom_object.assert_called_once()
    assert "failed to remove finalizer" in caplog.text
    assert "404" in caplog.text


def test_release_deleted_finalizer_patch_failure_succeeds_when_object_is_missing(
    caplog,
):
    api = _fake_api()
    api.patch_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    api.get_namespaced_custom_object.side_effect = _missing_object("test-flavor")

    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.INFO, logger="openstack_sync.hooks.framework.common"
        ):
            ok = hc.release_deleted_resource_finalizer(
                target=_target(),
                finalizer=FINALIZER,
                current_finalizers=[FINALIZER],
            )

    assert ok is True
    api.get_namespaced_custom_object.assert_called_once()
    assert "desired finalizer state" in caplog.text
    assert "failed to remove finalizer" not in caplog.text


def test_release_deleted_finalizer_patch_failure_fails_when_the_crd_is_missing(
    caplog,
):
    api = _fake_api()
    api.patch_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="Not Found"
    )
    api.get_namespaced_custom_object.side_effect = _not_found(MISSING_RESOURCE_BODY)

    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.ERROR, logger="openstack_sync.hooks.framework.common"
        ):
            ok = hc.release_deleted_resource_finalizer(
                target=_target(),
                finalizer=FINALIZER,
                current_finalizers=[FINALIZER],
            )

    assert ok is False
    assert "failed to verify finalizers" in caplog.text
    assert "failed to remove finalizer" in caplog.text


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


def test_patch_resource_status_uses_the_given_reason_on_failure():
    """A caller-supplied reason overrides the generic ReconcileError."""
    condition = _written_condition(
        sync_status="Failed", message="boom", reason="NautobotPrefixMissing"
    )

    assert condition["status"] == "False"
    assert condition["reason"] == "NautobotPrefixMissing"


def test_patch_resource_status_ignores_reason_when_synced():
    """A synced CR always reports Reconciled; there is nothing to disambiguate."""
    condition = _written_condition(
        sync_status="Synced", message="all good", reason="NautobotPrefixMissing"
    )

    assert condition["status"] == "True"
    assert condition["reason"] == "Reconciled"


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


# ---------------------------------------------------------------------------
# patch_resource_status: extra_status (plugin-supplied structured status)
# ---------------------------------------------------------------------------


def test_patch_resource_status_omits_extra_fields_when_not_given():
    """A plugin with no extra_status patches only the framework's own fields."""
    status = _patch().call_args.kwargs["body"]["status"]
    assert set(status.keys()) == {
        "syncStatus",
        "lastSyncTime",
        "message",
        "conditions",
        "observedGeneration",
    }


def test_patch_resource_status_merges_extra_status_into_the_body():
    status = _patch(
        extra_status={"prefixes": [{"id": "a", "cidr": "10.0.0.0/8"}]}
    ).call_args.kwargs["body"]["status"]

    assert status["prefixes"] == [{"id": "a", "cidr": "10.0.0.0/8"}]
    # The framework's own fields are still written alongside it, unchanged.
    assert status["syncStatus"] == "Synced"
    assert [c["type"] for c in status["conditions"]] == ["Ready"]


def test_patch_resource_status_skips_when_extra_status_also_matches():
    current = {**_matching_status(), "prefixes": [{"id": "a"}]}

    call = _patch(
        generation=1,
        message="ok",
        current_status=current,
        extra_status={"prefixes": [{"id": "a"}]},
    )

    assert not call.called


def test_patch_resource_status_patches_when_extra_status_differs():
    current = {**_matching_status(), "prefixes": [{"id": "a"}]}

    status = _patch(
        generation=1,
        message="ok",
        current_status=current,
        extra_status={"prefixes": [{"id": "b"}]},
    ).call_args.kwargs["body"]["status"]

    assert status["prefixes"] == [{"id": "b"}]


def test_patch_resource_status_patches_when_extra_status_key_is_new():
    """A CR whose stored status predates the extra field gets backfilled once."""
    current = _matching_status()
    assert "prefixes" not in current

    status = _patch(
        generation=1,
        message="ok",
        current_status=current,
        extra_status={"prefixes": []},
    ).call_args.kwargs["body"]["status"]

    assert status["prefixes"] == []


def test_patch_resource_status_skips_without_a_namespace(caplog):
    with caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.framework.common"):
        call = _patch(namespace=None)

    assert not call.called
    assert "no namespace to address it in" in caplog.text


def test_patch_resource_status_skips_on_unusable_crd_identity(caplog):
    with caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.framework.common"):
        call = _patch(crd_api_version="no-version-here")

    assert not call.called
    assert "cannot derive a CRD request target" in caplog.text


def test_patch_resource_status_logs_api_errors(caplog):
    api = _fake_api()
    api.patch_namespaced_custom_object_status.side_effect = ApiException(
        status=403, reason="Forbidden"
    )
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        with caplog.at_level(
            logging.ERROR, logger="openstack_sync.hooks.framework.common"
        ):
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


def _patch_status_with(exc: ApiException, name: str = "deleted-flavor") -> None:
    api = mock.MagicMock()
    api.patch_namespaced_custom_object_status.side_effect = exc
    with mock.patch.object(hc, "_customobjects_api", return_value=api):
        hc.patch_resource_status(
            name=name,
            namespace="openstack",
            generation=None,
            sync_status="Failed",
            message="already gone",
            crd_api_version=API_VERSION,
            crd_resource=RESOURCE,
            crd_kind="NeutronRouterFlavor",
            status_enabled=True,
        )


def test_patch_resource_status_does_not_error_when_the_cr_is_gone(caplog):
    """A CR deleted mid-reconcile is a race, not a fault."""
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.framework.common"):
        _patch_status_with(_missing_object("deleted-flavor"))

    assert "the CR is gone" in caplog.text
    assert "404" in caplog.text
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_patch_resource_status_warns_when_the_crd_is_the_thing_missing(caplog):
    """A 404 for the resource path is a chart or API configuration problem."""
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.framework.common"):
        _patch_status_with(_not_found(MISSING_RESOURCE_BODY))

    assert "failed to patch" in caplog.text
    assert [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_patch_resource_status_warns_when_denied_for_the_same_object(caplog):
    """Matching ``details.name`` alone must not turn an RBAC gap into success."""
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.framework.common"):
        _patch_status_with(_forbidden("deleted-flavor"))

    assert "failed to patch" in caplog.text
    assert "403" in caplog.text


def test_patch_resource_status_warns_when_a_404_names_a_different_object(caplog):
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.framework.common"):
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
    """Malformed 404 bodies must not escape the ApiException handler."""
    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.framework.common"):
        _patch_status_with(_not_found(body))

    assert "failed to patch" in caplog.text, shape
    assert [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_patch_resource_status_logs_unexpected_errors(caplog):
    with mock.patch.object(
        hc, "_customobjects_api", side_effect=RuntimeError("no kubeconfig")
    ):
        with caplog.at_level(
            logging.ERROR, logger="openstack_sync.hooks.framework.common"
        ):
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
