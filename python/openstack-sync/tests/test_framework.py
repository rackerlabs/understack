"""Tests for the generic sync framework.

Deliberately free of Neutron: the driver is exercised through a stub plugin, so
these tests describe the contract any future plugin can rely on.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from openstack_sync.hooks import framework
from openstack_sync.hooks.framework import HookConfig
from openstack_sync.hooks.framework import HookInputs
from openstack_sync.hooks.framework import SyncPlugin
from openstack_sync.hooks.framework import SyncResource
from openstack_sync.hooks.framework import build_crd_hook_config
from openstack_sync.hooks.framework import hook_inputs
from openstack_sync.hooks.framework import run_hook
from openstack_sync.hooks.framework import run_sync
from openstack_sync.hooks.framework import synced_message
from openstack_sync.plugins.common import ConfigError
from tests.conftest import CRD_API_VERSION
from tests.conftest import CRD_KIND
from tests.conftest import CRD_RESOURCE
from tests.conftest import make_hook_config

PREFIX = "NEUTRON_ROUTER_FLAVOR"
BINDING = "neutron-router-flavors"

ENV_NAMES = (
    "BINDING_CONTEXT_PATH",
    f"{PREFIX}_ENABLED",
    f"{PREFIX}_SYNC_CRONTAB",
    f"{PREFIX}_PRUNE",
    f"{PREFIX}_STATUS_ENABLED",
    f"{PREFIX}_READY_RETRIES",
    f"{PREFIX}_READY_DELAY",
    "POD_NAMESPACE",
)


def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Stub plugin
# ---------------------------------------------------------------------------


class StubPlugin(SyncPlugin):
    """Records what the driver asked it to do."""

    noun = "widget"

    def __init__(
        self,
        config: HookConfig,
        *,
        fail_for: tuple[str, ...] = (),
        notes_for: dict[str, list[str]] | None = None,
        prune_raises: bool = False,
    ) -> None:
        super().__init__(config)
        self.fail_for = set(fail_for)
        self.notes_for = notes_for or {}
        self.prune_raises = prune_raises
        self.reconciled: list[str] = []
        self.pruned: list[tuple[list[str], list[str]]] = []
        # One entry per prune call, in step with ``pruned``.
        self.swept: list[bool] = []
        self.waits = 0
        self.caches: list[Any] = []

    def wait_for_api(self, conn: Any) -> None:
        self.waits += 1

    def new_cache(self) -> Any:
        cache: dict[str, Any] = {}
        self.caches.append(cache)
        return cache

    def reconcile(self, conn: Any, spec: dict[str, Any], cache: Any) -> list[str]:
        name = spec["name"]
        self.reconciled.append(name)
        if name in self.fail_for:
            raise RuntimeError(f"reconcile failed for {name}")
        return list(self.notes_for.get(name, []))

    def prune(
        self,
        conn: Any,
        desired_specs: list[dict[str, Any]],
        *,
        deleted_specs: list[dict[str, Any]],
        sweep_unseen: bool,
    ) -> None:
        if self.prune_raises:
            raise RuntimeError("prune exploded")
        self.pruned.append(
            (
                [spec["name"] for spec in desired_specs],
                [spec["name"] for spec in deleted_specs],
            )
        )
        self.swept.append(sweep_unseen)


def _resource(
    name: str, secret: str = "infrasetup", cloud: str = "understack"
) -> SyncResource:
    return SyncResource(
        spec={"name": name},
        name=name,
        namespace="openstack",
        generation=1,
        secret_name=secret,
        cloud_name=cloud,
    )


def _inputs(
    reconcile: list[SyncResource],
    desired: list[SyncResource] | None = None,
    deleted: list[SyncResource] | None = None,
    prune_credentials: frozenset[tuple[str, str]] | None = None,
    unreadable: frozenset[str] = frozenset(),
) -> HookInputs:
    desired = reconcile if desired is None else desired
    deleted = deleted or []
    if prune_credentials is None:
        prune_credentials = frozenset(r.credentials for r in desired + deleted)
    return HookInputs(reconcile, desired, deleted, prune_credentials, unreadable)


def _drive(plugin: StubPlugin, inputs: HookInputs):
    """Run the driver with connections and status patching stubbed out."""
    with (
        mock.patch.object(framework, "get_openstack_connection") as connect,
        mock.patch.object(framework, "patch_resource_status") as patch_status,
    ):
        code = run_sync(plugin, inputs)
    return code, patch_status, connect


# ---------------------------------------------------------------------------
# HookConfig: the chart contract
# ---------------------------------------------------------------------------


def test_hook_config_reads_the_chart_contract(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{PREFIX}_STATUS_ENABLED", "true")
    monkeypatch.setenv(f"{PREFIX}_PRUNE", "true")
    monkeypatch.setenv(f"{PREFIX}_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.setenv(f"{PREFIX}_READY_RETRIES", "7")
    monkeypatch.setenv(f"{PREFIX}_READY_DELAY", "2.5")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    config = HookConfig.from_env(PREFIX, binding_name=BINDING)

    assert config.crd_api_version == CRD_API_VERSION
    assert config.crd_kind == CRD_KIND
    assert config.crd_resource == CRD_RESOURCE
    assert config.binding_name == BINDING
    assert config.namespace == "openstack"
    assert config.status_enabled is True
    assert config.prune is True
    assert config.sync_crontab == "0 * * * *"
    assert config.ready_retries == 7
    assert config.ready_delay == 2.5


def test_hook_config_defaults_are_off(monkeypatch):
    clear_env(monkeypatch)

    config = HookConfig.from_env(PREFIX, binding_name=BINDING)

    assert config.status_enabled is False
    assert config.prune is False
    assert config.sync_crontab == ""
    assert config.ready_retries == 30
    assert config.ready_delay == 10


def test_hook_config_requires_crd_identity(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.delenv(f"{PREFIX}_CRD_KIND", raising=False)

    with pytest.raises(ConfigError, match=f"{PREFIX}_CRD_KIND"):
        HookConfig.from_env(PREFIX, binding_name=BINDING)


# ---------------------------------------------------------------------------
# Hook config JSON
# ---------------------------------------------------------------------------


def test_disabled_hook_config_is_a_valid_noop(monkeypatch):
    clear_env(monkeypatch)

    config = build_crd_hook_config(PREFIX, BINDING)

    # shell-operator requires at least one binding, but a disabled hook must not
    # register Kubernetes watches it will never service.
    assert config["onStartup"] == 10
    assert "kubernetes" not in config
    assert "schedule" not in config


def test_disabled_hook_config_does_not_read_runtime_env(monkeypatch):
    """--config runs before the environment is guaranteed to be complete."""
    clear_env(monkeypatch)
    for name in (
        f"{PREFIX}_CRD_API_VERSION",
        f"{PREFIX}_CRD_KIND",
        f"{PREFIX}_CRD_RESOURCE",
    ):
        monkeypatch.delenv(name, raising=False)

    config = build_crd_hook_config(PREFIX, BINDING)

    assert config["onStartup"] == 10


def test_crontab_does_not_enable_a_disabled_hook(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{PREFIX}_SYNC_CRONTAB", "0 * * * *")

    config = build_crd_hook_config(PREFIX, BINDING)

    assert "schedule" not in config
    assert config["onStartup"] == 10


def test_enabled_hook_config_watches_the_crd(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{PREFIX}_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    config = build_crd_hook_config(PREFIX, BINDING)

    (binding,) = config["kubernetes"]
    assert binding["name"] == BINDING
    assert binding["apiVersion"] == CRD_API_VERSION
    assert binding["kind"] == CRD_KIND
    assert binding["executeHookOnEvent"] == ["Added", "Modified", "Deleted"]
    # The full object is needed: the reconcile reads spec and status.
    assert binding["jqFilter"] == "."
    assert binding["includeSnapshotsFrom"] == [BINDING]
    # A dedicated queue keeps a slow reconcile from blocking other hooks.
    assert binding["queue"] == BINDING
    assert binding["namespace"] == {"nameSelector": {"matchNames": ["openstack"]}}


def test_enabled_hook_config_omits_schedule_without_crontab(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{PREFIX}_ENABLED", "true")

    assert "schedule" not in build_crd_hook_config(PREFIX, BINDING)


def test_enabled_hook_config_adds_schedule_with_crontab(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{PREFIX}_SYNC_CRONTAB", "*/5 * * * *")

    (schedule,) = build_crd_hook_config(PREFIX, BINDING)["schedule"]

    assert schedule["crontab"] == "*/5 * * * *"
    assert schedule["includeSnapshotsFrom"] == [BINDING]
    assert schedule["queue"] == BINDING


def test_enabled_hook_config_omits_namespace_without_pod_namespace(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{PREFIX}_ENABLED", "true")

    (binding,) = build_crd_hook_config(PREFIX, BINDING)["kubernetes"]

    assert "namespace" not in binding


# ---------------------------------------------------------------------------
# Binding context -> HookInputs
# ---------------------------------------------------------------------------


def _cr(
    name: str,
    generation: int = 3,
    status: dict | None = None,
    secret: str = "infrasetup",
    cloud: str = "understack",
) -> dict:
    obj = {
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "metadata": {"name": name, "namespace": "openstack", "generation": generation},
        "spec": {
            "name": name,
            "cloudCredentialsRef": {
                "secretName": secret,
                "cloudName": cloud,
            },
        },
    }
    if status is not None:
        obj["status"] = status
    return obj


def test_hook_inputs_from_snapshot_reconciles_everything():
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Schedule",
            "snapshots": {BINDING: [{"object": _cr("b")}, {"object": _cr("a")}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    # Sorted so a run is deterministic.
    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["a", "b"]
    assert inputs.desired_resources_for_prune == inputs.resources_to_reconcile
    assert inputs.deleted_resources == []
    assert inputs.prune_credentials == frozenset({("infrasetup", "understack")})


def test_hook_inputs_from_synchronization():
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Synchronization",
            "objects": [{"object": _cr("a")}],
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["a"]


def test_hook_inputs_strips_cloud_credentials_from_spec():
    """A plugin must see only its own fields."""
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Schedule",
            "snapshots": {BINDING: [{"object": _cr("a")}]},
        }
    ]

    (resource,) = hook_inputs(contexts, config).resources_to_reconcile

    assert "cloudCredentialsRef" not in resource.spec
    assert resource.secret_name == "infrasetup"
    assert resource.cloud_name == "understack"


def test_hook_inputs_keeps_current_status():
    """The status is needed to break the status-patch feedback loop."""
    config = make_hook_config()
    status = {"syncStatus": "Synced", "observedGeneration": 3}
    contexts = [
        {
            "binding": BINDING,
            "type": "Schedule",
            "snapshots": {BINDING: [{"object": _cr("a", status=status)}]},
        }
    ]

    (resource,) = hook_inputs(contexts, config).resources_to_reconcile

    assert resource.current_status == status


def test_added_event_reconciles_only_the_changed_resource():
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Added",
            "object": _cr("new"),
            "snapshots": {BINDING: [{"object": _cr("new")}, {"object": _cr("old")}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["new"]
    # Prune still needs the full desired set, or it would delete "old".
    assert [r.spec["name"] for r in inputs.desired_resources_for_prune] == [
        "new",
        "old",
    ]


def test_event_prune_credentials_are_limited_to_changed_resource():
    config = make_hook_config()
    changed = _cr("changed", secret="group-a", cloud="cloud-a")
    other = _cr("other", secret="group-b", cloud="cloud-b")
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Modified",
            "object": changed,
            "snapshots": {BINDING: [{"object": changed}, {"object": other}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.desired_resources_for_prune] == [
        "changed",
        "other",
    ]
    assert inputs.prune_credentials == frozenset({("group-a", "cloud-a")})


def test_deleted_event_reconciles_nothing_but_prunes():
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Deleted",
            "object": _cr("gone"),
            "snapshots": {BINDING: [{"object": _cr("kept")}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["gone"]
    assert inputs.prune_credentials == frozenset({("infrasetup", "understack")})


def _event(watch_event: str, obj: dict, snapshot: list[dict] | None = None) -> dict:
    """Build one Event context.

    *snapshot* is the desired set the prune compares against. It defaults to the
    event's own object, as a live CR really sends. A Deleted event must say what
    is left instead: a snapshot still listing it would make a prune test pass
    while the prune does nothing.
    """
    assert not (
        watch_event == "Deleted" and snapshot is None
    ), "a Deleted event needs its snapshot spelled out"
    return {
        "binding": BINDING,
        "type": "Event",
        "watchEvent": watch_event,
        "object": obj,
        "snapshots": {BINDING: [{"object": obj}] if snapshot is None else snapshot},
    }


def test_repeated_events_for_one_cr_reconcile_it_once():
    """A failing run accumulates a backlog; one CR must stay one reconcile."""
    config = make_hook_config()
    live = _cr("probe", generation=3)
    contexts = [
        _event("Added", _cr("probe", generation=1), [{"object": live}]),
        _event("Modified", _cr("probe", generation=2), [{"object": live}]),
        _event("Modified", live, [{"object": live}]),
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["probe"]
    # The last event is the current one.
    assert inputs.resources_to_reconcile[0].generation == 3


def test_collapsed_batch_still_prunes_against_the_whole_snapshot():
    """A backlog for one CR must not narrow the desired set the prune sees.

    The snapshot names every CR that should exist; pruning against less deletes
    a resource whose CR is still there.
    """
    config = make_hook_config(prune=True, status_enabled=True)
    live = _cr("probe", generation=3)
    snapshot = [{"object": live}, {"object": _cr("untouched")}]
    contexts = [_event("Added", _cr("probe", generation=1), snapshot)]
    contexts += [_event("Modified", live, snapshot) for _ in range(29)]

    inputs = hook_inputs(contexts, config)
    plugin = StubPlugin(config)
    code, patch_status, _ = _drive(plugin, inputs)

    assert code == 0
    assert plugin.reconciled == ["probe"]
    assert patch_status.call_count == 1
    assert plugin.pruned == [(["probe", "untouched"], [])]


def test_a_recreate_after_a_delete_in_the_same_batch_is_reconciled():
    """Order decides: a change after a Deleted is a new CR under the same name."""
    config = make_hook_config()
    recreated = _cr("probe", generation=1)
    contexts = [
        _event("Deleted", _cr("probe", generation=7), []),
        _event("Added", recreated, [{"object": recreated}]),
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.generation for r in inputs.resources_to_reconcile] == [1]
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["probe"]


def test_deleted_event_cancels_an_earlier_change_in_the_same_batch():
    config = make_hook_config()
    contexts = [
        _event("Added", _cr("probe"), []),
        _event("Modified", _cr("probe"), []),
        _event("Deleted", _cr("probe"), []),
    ]

    inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["probe"]
    assert inputs.prune_credentials == frozenset({("infrasetup", "understack")})


def test_repeated_delete_events_prune_once():
    config = make_hook_config()
    contexts = [
        _event("Deleted", _cr("probe"), []),
        _event("Deleted", _cr("probe"), []),
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.deleted_resources] == ["probe"]


def test_distinct_crs_in_one_batch_are_all_reconciled():
    config = make_hook_config()
    snapshot = [{"object": _cr("a")}, {"object": _cr("b")}]
    contexts = [
        _event("Added", _cr("a"), snapshot),
        _event("Modified", _cr("b"), snapshot),
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["a", "b"]


def test_a_deleted_cr_does_not_wedge_the_reconcile(caplog):
    """Replays a backlog of events for a CR that was deleted mid-backlog.

    Shell-operator replays the whole backlog on every retry, so a failing run
    keeps being handed events for an object that is already gone. None of them
    is reconciled and no status is written for it. The prune still reports,
    because a cloud it cannot reach is not one it can safely sweep -- that is
    the only failure left, where there were once one per queued event.
    """
    config = make_hook_config(prune=True, status_enabled=True)

    def gone() -> dict:
        return _cr("zz-probe", secret="missing-secret")

    contexts = [_event("Added", gone(), [])]
    contexts += [_event("Modified", gone(), []) for _ in range(30)]
    contexts += [_event("Deleted", gone(), [])]

    inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["zz-probe"]

    plugin = StubPlugin(config)
    with (
        mock.patch.object(
            framework,
            "get_openstack_connection",
            side_effect=RuntimeError('secrets "missing-secret" not found'),
        ),
        mock.patch.object(framework, "patch_resource_status") as patch_status,
        caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.framework"),
    ):
        code = run_sync(plugin, inputs)

    assert plugin.reconciled == []
    assert patch_status.call_count == 0
    assert code == 1
    assert "Cannot build an OpenStack connection for the widget prune" in caplog.text
    assert "failed to reconcile" not in caplog.text


def test_event_without_watch_event_is_ignored_without_snapshot_reconcile(caplog):
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "object": _cr("bad"),
            "snapshots": {BINDING: [{"object": _cr("kept")}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []
    assert [r.spec["name"] for r in inputs.desired_resources_for_prune] == ["kept"]
    assert inputs.prune_credentials == frozenset()
    assert "event carries no watchEvent" in caplog.text


def test_modified_event_skipped_when_status_already_current():
    """The hook's own status patch must not trigger another reconcile."""
    config = make_hook_config()
    current = {"syncStatus": "Synced", "observedGeneration": 3}
    obj = _cr("a", generation=3, status=current)
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Modified",
            "object": obj,
            "snapshots": {BINDING: [{"object": obj}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []


def test_modified_event_reconciles_when_generation_bumped():
    config = make_hook_config()
    stale = {"syncStatus": "Synced", "observedGeneration": 2}
    obj = _cr("a", generation=3, status=stale)
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Modified",
            "object": obj,
            "snapshots": {BINDING: [{"object": obj}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["a"]


def test_event_context_without_snapshot_is_an_error():
    config = make_hook_config()
    contexts = [
        {"binding": BINDING, "type": "Event", "watchEvent": "Added", "object": _cr("a")}
    ]

    with pytest.raises(ConfigError, match="snapshot"):
        hook_inputs(contexts, config)


def test_unrecognised_context_is_an_error():
    config = make_hook_config()

    with pytest.raises(ConfigError, match="does not contain"):
        hook_inputs([{"binding": "something-else", "type": "Event"}], config)


# ---------------------------------------------------------------------------
# Unreadable CRs
# ---------------------------------------------------------------------------


def _cr_without_credentials(name: str, generation: int = 1) -> dict:
    return {
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "metadata": {"name": name, "namespace": "openstack", "generation": generation},
        "spec": {"name": name},
    }


def _snapshot_context(*objects: dict) -> list[dict]:
    return [
        {
            "binding": BINDING,
            "type": "Schedule",
            "snapshots": {BINDING: [{"object": obj} for obj in objects]},
        }
    ]


def test_unreadable_cr_does_not_discard_the_readable_ones():
    config = make_hook_config()
    contexts = _snapshot_context(
        _cr("good"), _cr_without_credentials("legacy"), _cr("also-good")
    )

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == [
        "also-good",
        "good",
    ]
    assert inputs.unreadable_resources == frozenset({"openstack/legacy"})


def test_unreadable_cr_is_reported_by_namespace_and_name(caplog):
    """Naming the field is not enough; the report must identify the object."""
    config = make_hook_config()

    hook_inputs(_snapshot_context(_cr_without_credentials("legacy")), config)

    assert "openstack/legacy" in caplog.text
    assert "cloudCredentialsRef" in caplog.text


@pytest.mark.parametrize(
    ("creds", "reason"),
    [
        ({"cloudName": "understack"}, "secretName absent"),
        ({"secretName": "infrasetup"}, "cloudName absent"),
        ({"secretName": "", "cloudName": "understack"}, "secretName empty"),
        ({"secretName": "infrasetup", "cloudName": ""}, "cloudName empty"),
        ({}, "both absent"),
        ("infrasetup", "not an object"),
        (None, "explicitly null"),
    ],
)
def test_incomplete_cloud_credentials_ref_is_unreadable(creds, reason):
    config = make_hook_config()
    obj = _cr_without_credentials("legacy")
    obj["spec"]["cloudCredentialsRef"] = creds

    inputs = hook_inputs(_snapshot_context(obj, _cr("good")), config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["good"], reason
    assert inputs.unreadable_resources == frozenset({"openstack/legacy"}), reason


def test_cr_without_a_spec_is_unreadable():
    config = make_hook_config()
    obj = _cr_without_credentials("legacy")
    del obj["spec"]

    inputs = hook_inputs(_snapshot_context(obj, _cr("good")), config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["good"]
    assert inputs.unreadable_resources == frozenset({"openstack/legacy"})


def test_unreadable_cr_in_synchronization_is_dropped():
    """The startup path: shell-operator hands over every existing CR at once."""
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Synchronization",
            "objects": [_cr_without_credentials("legacy"), _cr("good")],
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["good"]
    assert inputs.unreadable_resources == frozenset({"openstack/legacy"})


def test_unreadable_cr_event_is_dropped():
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Added",
            "object": _cr_without_credentials("legacy"),
            "snapshots": {BINDING: [{"object": _cr("good")}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []
    assert inputs.unreadable_resources == frozenset({"openstack/legacy"})


def test_unreadable_delete_event_is_dropped_without_holding_back_the_prune(caplog):
    """A CR that cannot be read cannot drive a deletion, but is not missing either.

    A deleted CR was never in the desired set, so counting it as unreadable
    would skip the prune on every replay of that batch -- forever.
    """
    config = make_hook_config()
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Deleted",
            "object": _cr_without_credentials("legacy"),
            "snapshots": {BINDING: [{"object": _cr("good")}]},
        }
    ]

    with caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.framework"):
        inputs = hook_inputs(contexts, config)

    assert inputs.deleted_resources == []
    assert inputs.unreadable_resources == frozenset()
    assert "Ignoring unreadable Deleted CR openstack/legacy" in caplog.text


def test_unreadable_cr_is_reported_once_across_event_and_snapshot():
    """The changed object is also in its own snapshot; report the CR, not sightings."""
    config = make_hook_config()
    legacy = _cr_without_credentials("legacy")
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Modified",
            "object": legacy,
            "snapshots": {BINDING: [{"object": legacy}, {"object": _cr("good")}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert inputs.unreadable_resources == frozenset({"openstack/legacy"})


def test_readable_crs_leave_nothing_unreadable():
    config = make_hook_config()

    inputs = hook_inputs(_snapshot_context(_cr("a"), _cr("b")), config)

    assert inputs.unreadable_resources == frozenset()


def test_unreadable_crs_do_not_stall_a_whole_namespace():
    config = make_hook_config(prune=True)
    plugin = StubPlugin(config)
    contexts = [
        {
            "binding": BINDING,
            "type": "Synchronization",
            "objects": [
                _cr_without_credentials("bmc-maintenance"),
                _cr_without_credentials("firmware-update-r740xd"),
                _cr_without_credentials("firmware-update-r7615"),
                _cr("firmware-bios-r740xd"),
                _cr("firmware-idrac9"),
            ],
        }
    ]

    inputs = hook_inputs(contexts, config)
    code, patch_status, _ = _drive(plugin, inputs)

    assert plugin.reconciled == ["firmware-bios-r740xd", "firmware-idrac9"]
    statuses = {call.kwargs["sync_status"] for call in patch_status.call_args_list}
    assert statuses == {"Synced"}
    # Reported in the log, not the exit code: these three stay unreadable on
    # every retry, and a failing run blocks this hook's queue.
    assert code == 0
    assert plugin.pruned == []
    assert inputs.unreadable_resources == frozenset(
        {
            "openstack/bmc-maintenance",
            "openstack/firmware-update-r740xd",
            "openstack/firmware-update-r7615",
        }
    )


# ---------------------------------------------------------------------------
# run_sync
# ---------------------------------------------------------------------------


def test_run_sync_reconciles_and_reports_synced():
    plugin = StubPlugin(make_hook_config())

    code, patch_status, _ = _drive(plugin, _inputs([_resource("a"), _resource("b")]))

    assert code == 0
    assert plugin.reconciled == ["a", "b"]
    statuses = [call.kwargs["sync_status"] for call in patch_status.call_args_list]
    assert statuses == ["Synced", "Synced"]
    assert patch_status.call_args_list[0].kwargs["message"] == (
        "Successfully reconciled widget"
    )


def test_run_sync_waits_for_api_once_per_credential_group():
    plugin = StubPlugin(make_hook_config())
    resources = [
        _resource("a"),
        _resource("b"),
        _resource("c", secret="other", cloud="other-cloud"),
    ]

    _drive(plugin, _inputs(resources))

    assert plugin.waits == 2
    # One cache per group, so lookups are shared within a group but not across.
    assert len(plugin.caches) == 2


def test_run_sync_connects_with_each_resources_own_credentials():
    plugin = StubPlugin(make_hook_config())
    resources = [
        _resource("a", secret="secret-a", cloud="cloud-a"),
        _resource("b", secret="secret-b", cloud="cloud-b"),
    ]

    _, _, connect = _drive(plugin, _inputs(resources))

    assert sorted(call.args for call in connect.call_args_list) == [
        ("secret-a", "cloud-a"),
        ("secret-b", "cloud-b"),
    ]


def test_run_sync_forwards_crd_identity_and_current_status_to_the_patch():
    """Forward everything patch_resource_status needs.

    The CRD identity addresses the object on the API, and the current status
    decides whether the patch can be skipped.
    """
    config = make_hook_config(status_enabled=True)
    plugin = StubPlugin(config)
    status = {"syncStatus": "Synced", "observedGeneration": 1}
    resource = SyncResource(
        spec={"name": "a"},
        name="a",
        namespace="openstack",
        generation=1,
        secret_name="infrasetup",
        cloud_name="understack",
        current_status=status,
    )

    _, patch_status, _ = _drive(plugin, _inputs([resource]))

    kwargs = patch_status.call_args.kwargs
    assert kwargs["crd_resource"] == CRD_RESOURCE
    assert kwargs["crd_kind"] == CRD_KIND
    assert kwargs["status_enabled"] is True
    assert kwargs["current_status"] == status
    assert kwargs["generation"] == 1
    assert kwargs["namespace"] == "openstack"


def test_run_sync_reports_notes_without_failing():
    plugin = StubPlugin(make_hook_config(), notes_for={"a": ["thing drifted"]})

    code, patch_status, _ = _drive(plugin, _inputs([_resource("a")]))

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    message = patch_status.call_args.kwargs["message"]
    assert message.startswith("Successfully reconciled widget")
    assert "thing drifted" in message


def test_run_sync_marks_failure_and_does_not_sweep():
    """A failed reconcile leaves the desired set unsafe to delete by absence.

    Nothing was deleted here, so there is no prune to run at all -- but the run
    still reports failure so shell-operator retries it.
    """
    plugin = StubPlugin(make_hook_config(prune=True), fail_for=("b",))

    code, patch_status, _ = _drive(plugin, _inputs([_resource("a"), _resource("b")]))

    assert code == 1
    assert plugin.pruned == []
    by_name = {
        call.kwargs["name"]: call.kwargs["sync_status"]
        for call in patch_status.call_args_list
    }
    assert by_name == {"a": "Synced", "b": "Failed"}


def test_run_sync_still_deletes_a_removed_cr_when_another_failed():
    """A deletion names its resource, so an unrelated failure cannot make it wrong.

    The failing CR stays in the desired set and so stays protected; only the
    absence-based sweep is withheld.
    """
    plugin = StubPlugin(make_hook_config(prune=True), fail_for=("broken",))
    broken = _resource("broken")
    gone = _resource("gone")
    inputs = _inputs([broken], desired=[broken], deleted=[gone])

    code, _, _ = _drive(plugin, inputs)

    assert code == 1
    assert plugin.pruned == [(["broken"], ["gone"])]
    assert plugin.swept == [False]


def test_run_sync_continues_after_one_failure():
    plugin = StubPlugin(make_hook_config(), fail_for=("a",))

    _drive(plugin, _inputs([_resource("a"), _resource("b")]))

    assert plugin.reconciled == ["a", "b"]


def test_run_sync_marks_whole_group_failed_when_connection_fails():
    plugin = StubPlugin(make_hook_config())
    inputs = _inputs([_resource("a"), _resource("b")])

    with (
        mock.patch.object(
            framework,
            "get_openstack_connection",
            side_effect=RuntimeError("no route to keystone"),
        ),
        mock.patch.object(framework, "patch_resource_status") as patch_status,
    ):
        code = run_sync(plugin, inputs)

    assert code == 1
    assert plugin.reconciled == []
    statuses = {call.kwargs["sync_status"] for call in patch_status.call_args_list}
    assert statuses == {"Failed"}
    assert "no route to keystone" in patch_status.call_args.kwargs["message"]


def test_run_sync_marks_group_failed_when_api_never_becomes_ready():
    class NeverReady(StubPlugin):
        def wait_for_api(self, conn):
            raise RuntimeError("api not ready")

    plugin = NeverReady(make_hook_config())

    code, patch_status, _ = _drive(plugin, _inputs([_resource("a")]))

    assert code == 1
    assert plugin.reconciled == []
    assert patch_status.call_args.kwargs["sync_status"] == "Failed"
    assert "api not ready" in patch_status.call_args.kwargs["message"]


def test_run_sync_prunes_after_successful_reconcile():
    plugin = StubPlugin(make_hook_config(prune=True))

    code, _, _ = _drive(plugin, _inputs([_resource("a")]))

    assert code == 0
    assert plugin.pruned == [(["a"], [])]


def test_run_sync_passes_the_deleted_specs_for_deleted_credentials():
    """A confirmed deletion lets prune act on an empty desired set."""
    plugin = StubPlugin(make_hook_config(prune=True))
    deleted = _resource("gone")
    inputs = _inputs([], desired=[], deleted=[deleted])

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    assert plugin.pruned == [([], ["gone"])]


def test_run_sync_prunes_against_every_credentials_desired_resources():
    """Prune is scoped by ownership marker, not by credentials, so the set is the union.

    Here the credential whose only CR was deleted has an empty desired set of
    its own, and can still list what the other credential manages. It is handed
    every group's desired names, which is what keeps the resource the other
    group still wants from being a prune candidate.
    """
    plugin = StubPlugin(make_hook_config(prune=True))
    keeper = _resource("keeper", secret="infrasetup", cloud="understack")
    gone = _resource("gone", secret="infrasetup-system", cloud="understack")
    inputs = _inputs([keeper], desired=[keeper], deleted=[gone])

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    # Sorted by credentials: infrasetup, then infrasetup-system. The second
    # group's own desired set is empty, and it still sees keeper.
    assert plugin.pruned == [(["keeper"], []), (["keeper"], ["gone"])]


def test_run_sync_keeps_a_resource_another_credential_wants_off_the_prune_list():
    """The bug the union closes, stated on its own.

    Both credentials still want a resource, and each prunes with a connection
    that can list what the other manages -- a system-scoped token sees another
    project's runbooks, and every token sees what is public. Prune filters by an
    ownership marker that records no credential, so a per-credential desired set
    would offer the other group's resource up for deletion.
    """
    plugin = StubPlugin(make_hook_config(prune=True))
    mine = _resource("mine", secret="infrasetup", cloud="understack")
    theirs = _resource("theirs", secret="infrasetup-system", cloud="understack")
    inputs = _inputs([mine, theirs])

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    # Neither call may omit a name the other credential still wants.
    assert [sorted(names) for names, _ in plugin.pruned] == [
        ["mine", "theirs"],
        ["mine", "theirs"],
    ]


def test_run_sync_skips_prune_for_credentials_with_no_desired_resources():
    """An empty desired set with no deletion may be an unreadable snapshot."""
    plugin = StubPlugin(make_hook_config(prune=True))
    inputs = HookInputs(
        [], [], [], frozenset({("infrasetup", "understack")}), frozenset()
    )

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    assert plugin.pruned == []


def test_run_sync_connects_to_prune_a_deletion_whatever_prune_says():
    """A deletion reconciles nothing, so the prune opens the connection itself.

    ``PRUNE`` is the plugin's flag, not the driver's: a prune can have work the
    flag does not gate, so the driver hands over a connection and lets the
    plugin decide. It does not wait for the API first -- the prune's own first
    call is the probe.
    """
    plugin = StubPlugin(make_hook_config(prune=False))
    inputs = _inputs([], desired=[], deleted=[_resource("gone")])

    code, _, connect = _drive(plugin, inputs)

    assert code == 0
    assert connect.call_count == 1
    assert plugin.waits == 0
    assert plugin.pruned == [([], ["gone"])]


def test_run_sync_reports_a_prune_whose_connection_cannot_be_built():
    """Credentials that cannot be loaded fail the run rather than pruning."""
    plugin = StubPlugin(make_hook_config(prune=True))
    inputs = _inputs([], desired=[], deleted=[_resource("gone")])

    with (
        mock.patch.object(
            framework,
            "get_openstack_connection",
            side_effect=RuntimeError("no clouds.yaml in secret"),
        ),
        mock.patch.object(framework, "patch_resource_status"),
    ):
        code = run_sync(plugin, inputs)

    assert code == 1
    assert plugin.pruned == []


def test_run_sync_returns_error_when_prune_fails():
    plugin = StubPlugin(make_hook_config(prune=True), prune_raises=True)

    code, _, _ = _drive(plugin, _inputs([_resource("a")]))

    assert code == 1


def test_run_sync_skips_prune_when_a_cr_was_unreadable():
    """An unreadable CR withholds every prune, deletions included.

    Its resource names cannot be read, so they cannot be subtracted from the
    deletions either, and a deletion naming one of them is indistinguishable
    from a real removal.
    """
    plugin = StubPlugin(make_hook_config(prune=True))
    inputs = _inputs(
        [_resource("a")],
        deleted=[_resource("gone")],
        unreadable=frozenset({"openstack/legacy"}),
    )

    code, _, _ = _drive(plugin, inputs)

    assert plugin.pruned == []
    assert code == 0


def test_run_sync_does_not_fail_the_run_for_an_unreadable_cr_alone():
    """A malformed CR is stored state, so a non-zero exit could only wedge us.

    Shell-operator re-runs a failing hook and blocks the rest of its queue until
    it succeeds. An unreadable CR is unreadable on every retry, so reporting it
    as a failure would stop the readable CRs from reconciling for good.
    """
    plugin = StubPlugin(make_hook_config(prune=True))
    inputs = _inputs([_resource("a")], unreadable=frozenset({"openstack/legacy"}))

    code, _, _ = _drive(plugin, inputs)

    assert code == 0


def test_run_sync_fails_when_a_reconcile_failed_alongside_an_unreadable_cr():
    """The retryable failure still decides the exit code."""
    plugin = StubPlugin(make_hook_config(prune=True), fail_for=("a",))
    inputs = _inputs([_resource("a")], unreadable=frozenset({"openstack/legacy"}))

    code, _, _ = _drive(plugin, inputs)

    assert code == 1
    assert plugin.pruned == []


def test_run_sync_reconciles_readable_crs_despite_an_unreadable_one():
    plugin = StubPlugin(make_hook_config())
    inputs = _inputs(
        [_resource("a"), _resource("b")], unreadable=frozenset({"openstack/legacy"})
    )

    code, patch_status, _ = _drive(plugin, inputs)

    # The error log keeps the problem visible; the healthy CRs still converge and
    # still get their status patched.
    assert code == 0
    assert plugin.reconciled == ["a", "b"]
    statuses = {call.kwargs["sync_status"] for call in patch_status.call_args_list}
    assert statuses == {"Synced"}


def test_run_sync_names_every_unreadable_cr(caplog):
    plugin = StubPlugin(make_hook_config())
    unreadable = frozenset({"openstack/bmc-maintenance", "openstack/firmware-update"})

    _drive(plugin, _inputs([_resource("a")], unreadable=unreadable))

    for identity in unreadable:
        assert identity in caplog.text


def test_run_sync_skips_status_patch_without_metadata_name():
    plugin = StubPlugin(make_hook_config())
    nameless = SyncResource(
        spec={"name": "a"},
        name=None,
        namespace="openstack",
        generation=1,
        secret_name="infrasetup",
        cloud_name="understack",
    )

    code, patch_status, _ = _drive(plugin, _inputs([nameless]))

    assert code == 0
    patch_status.assert_not_called()


def test_synced_message_is_unqualified_without_notes():
    assert synced_message("widget", []) == "Successfully reconciled widget"


def test_synced_message_lists_every_note():
    message = synced_message("widget", ["first", "second"])

    assert "first" in message
    assert "second" in message


# ---------------------------------------------------------------------------
# run_hook
# ---------------------------------------------------------------------------


def _write_context(path: Path, payload: str) -> str:
    context_path = path / "binding-context.json"
    context_path.write_text(payload, encoding="utf-8")
    return str(context_path)


def test_run_hook_prints_config_and_exits(monkeypatch, capsys):
    monkeypatch.setattr(framework.sys, "argv", ["hook.py", "--config"])

    code = run_hook(lambda: {"configVersion": "v1"}, lambda contexts: 99)

    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"configVersion": "v1"}


def test_run_hook_returns_zero_without_context_path(monkeypatch):
    monkeypatch.setattr(framework.sys, "argv", ["hook.py"])
    monkeypatch.delenv("BINDING_CONTEXT_PATH", raising=False)
    called = []

    code = run_hook(dict, lambda contexts: called.append(contexts) or 0)

    assert code == 0
    assert called == []


def test_run_hook_returns_zero_on_empty_context(monkeypatch, tmp_path):
    monkeypatch.setattr(framework.sys, "argv", ["hook.py"])
    monkeypatch.setenv("BINDING_CONTEXT_PATH", _write_context(tmp_path, "   "))
    called = []

    code = run_hook(dict, lambda contexts: called.append(contexts) or 0)

    assert code == 0
    assert called == []


def test_run_hook_returns_error_on_invalid_json(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(framework.sys, "argv", ["hook.py"])
    monkeypatch.setenv("BINDING_CONTEXT_PATH", _write_context(tmp_path, "{not json"))

    code = run_hook(dict, lambda contexts: 0)

    assert code == 1
    assert "binding context" in caplog.text


def test_run_hook_returns_error_when_context_is_not_a_list(monkeypatch, tmp_path):
    monkeypatch.setattr(framework.sys, "argv", ["hook.py"])
    monkeypatch.setenv("BINDING_CONTEXT_PATH", _write_context(tmp_path, '{"a": 1}'))

    assert run_hook(dict, lambda contexts: 0) == 1


def test_run_hook_converts_an_unexpected_error_into_exit_one(monkeypatch, tmp_path):
    monkeypatch.setattr(framework.sys, "argv", ["hook.py"])
    monkeypatch.setenv("BINDING_CONTEXT_PATH", _write_context(tmp_path, "[{}]"))

    def boom(contexts):
        raise ConfigError("bad spec")

    assert run_hook(dict, boom) == 1


def test_run_hook_logs_the_exception_type_and_traceback(monkeypatch, tmp_path, caplog):
    """str(exc) alone is not a usable report.

    A KeyError stringifies to nothing but the missing key, so logging only the
    message yields a line like ``'cloudCredentialsRef'`` -- no type, no CR, no
    location. The type and the traceback are what make the failure diagnosable.
    """
    monkeypatch.setattr(framework.sys, "argv", ["hook.py"])
    monkeypatch.setenv("BINDING_CONTEXT_PATH", _write_context(tmp_path, "[{}]"))

    def boom(contexts):
        raise KeyError("cloudCredentialsRef")

    assert run_hook(dict, boom) == 1
    assert "KeyError" in caplog.text
    assert "cloudCredentialsRef" in caplog.text
    assert "Traceback" in caplog.text
