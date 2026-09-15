"""Tests for the generic sync framework.

Deliberately free of Neutron: the driver is exercised through a stub plugin, so
these tests describe the contract any future plugin can rely on.
"""

from __future__ import annotations

import ast
import json
import logging
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from openstack_sync.hooks import framework
from openstack_sync.hooks.framework import CleanupPolicy
from openstack_sync.hooks.framework import CredentialKey
from openstack_sync.hooks.framework import HookConfig
from openstack_sync.hooks.framework import PruneRequest
from openstack_sync.hooks.framework import SyncPlan
from openstack_sync.hooks.framework import SyncPlugin
from openstack_sync.hooks.framework import SyncResource
from openstack_sync.hooks.framework import build_crd_hook_config
from openstack_sync.hooks.framework import group_by_credentials
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
HOOKS_DIR = Path(__file__).parents[1] / "openstack_sync" / "hooks"

FRAMEWORK_PUBLIC_NAMES = [
    "CleanupPolicy",
    "CredentialKey",
    "FINALIZER",
    "HookConfig",
    "PruneRequest",
    "SyncPlan",
    "SyncPlugin",
    "SyncResource",
    "add_resource_finalizer",
    "build_crd_hook_config",
    "get_openstack_connection",
    "group_by_credentials",
    "hook_enabled",
    "hook_inputs",
    "patch_resource_status",
    "release_deleted_resource_finalizer",
    "remove_resource_finalizer",
    "run_hook",
    "run_sync",
    "synced_message",
]

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


def _framework_imports(path: Path) -> list[str]:
    imports: list[str] = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(
                alias.name
                for alias in node.names
                if alias.name == "openstack_sync.hooks.framework"
            )
        elif isinstance(node, ast.ImportFrom):
            if node.module == "openstack_sync.hooks.framework":
                imports.append(node.module)
            elif node.module == "openstack_sync.hooks":
                imports.extend(
                    f"{node.module}.{alias.name}"
                    for alias in node.names
                    if alias.name == "framework"
                )
    return imports


def _framework_imported_names(path: Path) -> set[str]:
    imports: set[str] = set()
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == "openstack_sync.hooks.framework":
                imports.update(alias.name for alias in node.names)
    return imports


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
        self.pruned: list[tuple[list[str], bool]] = []
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
        authoritative_empty: bool,
    ) -> None:
        if self.prune_raises:
            raise RuntimeError("prune exploded")
        self.pruned.append(
            ([spec["name"] for spec in desired_specs], authoritative_empty)
        )


class NoPrunePlugin(SyncPlugin):
    """Plugin that intentionally inherits the framework's no-op prune."""

    noun = "no-prune widget"

    def __init__(self, config: HookConfig) -> None:
        super().__init__(config)
        self.reconciled: list[str] = []
        self.waits = 0

    def wait_for_api(self, conn: Any) -> None:
        self.waits += 1

    def reconcile(self, conn: Any, spec: dict[str, Any], cache: Any) -> list[str]:
        self.reconciled.append(spec["name"])
        return []


class AlwaysPrunePlugin(StubPlugin):
    """Plugin whose prune is best-effort, so it runs even when PRUNE is off.

    Mirrors RouterFlavorPlugin: it overrides cleanup_policy to run a
    non-destructive sweep without holding CR deletion on a finalizer.
    """

    noun = "always-prune widget"

    def cleanup_policy(self) -> CleanupPolicy:
        if self.config.prune:
            return CleanupPolicy.FINALIZED_PRUNE
        return CleanupPolicy.BEST_EFFORT_PRUNE


class RequestPrunePlugin(StubPlugin):
    """Plugin using the new request-shaped prune API."""

    def __init__(self, config: HookConfig) -> None:
        super().__init__(config)
        self.prune_requests: list[PruneRequest] = []

    def prune_resources(self, conn: Any, request: PruneRequest) -> None:
        self.prune_requests.append(request)


def _resource(
    name: str,
    secret: str = "infrasetup",
    cloud: str = "understack",
    finalizers: tuple[str, ...] = (),
    deletion_timestamp: str | None = None,
    resource_version: str | None = None,
    uid: str | None = None,
) -> SyncResource:
    return SyncResource(
        spec={"name": name},
        name=name,
        namespace="openstack",
        generation=1,
        secret_name=secret,
        cloud_name=cloud,
        finalizers=finalizers,
        deletion_timestamp=deletion_timestamp,
        resource_version=resource_version,
        uid=uid,
    )


def _inputs(
    reconcile: list[SyncResource],
    desired: list[SyncResource] | None = None,
    deleted: list[SyncResource] | None = None,
    prune_credentials: frozenset[tuple[str, str]] | None = None,
    unreadable: frozenset[str] = frozenset(),
) -> SyncPlan:
    desired = reconcile if desired is None else desired
    deleted = deleted or []
    if prune_credentials is None:
        prune_credentials = frozenset(r.credentials for r in desired + deleted)
    return SyncPlan(reconcile, desired, deleted, prune_credentials, unreadable)


def test_group_by_credentials_is_public_contract():
    resources = [
        _resource("first", secret="alpha", cloud="understack"),
        _resource("other-cloud", secret="alpha", cloud="region-two"),
        _resource("second", secret="alpha", cloud="understack"),
    ]
    expected_key: CredentialKey = ("alpha", "understack")

    grouped = group_by_credentials(resources)

    assert list(grouped) == [expected_key, ("alpha", "region-two")]
    assert [r.spec["name"] for r in grouped[expected_key]] == ["first", "second"]


def test_cleanup_policy_boolean_accessors_report_policy_decisions():
    class PolicyPlugin(StubPlugin):
        def cleanup_policy(self) -> CleanupPolicy:
            return CleanupPolicy.BEST_EFFORT_PRUNE

    plugin = PolicyPlugin(make_hook_config(prune=False))

    assert plugin.should_run_prune() is True
    assert plugin.uses_finalizer() is False


def test_framework_public_facade_exports_expected_names():
    assert framework.__all__ == FRAMEWORK_PUBLIC_NAMES
    for name in FRAMEWORK_PUBLIC_NAMES:
        assert hasattr(framework, name)


def test_framework_public_facade_covers_hook_imports():
    public_names = set(framework.__all__)
    for path in sorted(HOOKS_DIR.glob("*.py")):
        imported_names = _framework_imported_names(path)
        assert imported_names <= public_names, (
            path.name,
            imported_names - public_names,
        )


def test_framework_import_boundary_keeps_facade_at_edges():
    framework_modules = {
        "common.py",
        "config.py",
        "contracts.py",
        "entrypoint.py",
        "finalizers.py",
        "planner.py",
        "pruning.py",
        "resources.py",
        "runner.py",
        "status.py",
    }
    hook_entrypoints = {
        "ironic_runbooks.py",
        "placeholder.py",
        "router_flavors.py",
    }

    for module_name in framework_modules:
        assert (
            _framework_imports(HOOKS_DIR / "framework" / module_name) == []
        ), module_name
    for module_name in hook_entrypoints:
        assert _framework_imports(HOOKS_DIR / module_name), module_name


def _drive(plugin: StubPlugin, inputs: SyncPlan):
    """Run the driver with connections and status patching stubbed out."""
    with (
        mock.patch.object(framework, "get_openstack_connection") as connect,
        mock.patch.object(framework, "patch_resource_status") as patch_status,
        mock.patch.object(framework, "add_resource_finalizer", return_value=True),
        mock.patch.object(framework, "remove_resource_finalizer", return_value=True),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ),
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
# Binding context -> SyncPlan
# ---------------------------------------------------------------------------


def _cr(
    name: str,
    generation: int = 3,
    status: dict | None = None,
    secret: str = "infrasetup",
    cloud: str = "understack",
    finalizers: list[str] | None = None,
    deletion_timestamp: str | None = None,
    uid: str | None = None,
) -> dict:
    metadata: dict[str, Any] = {
        "name": name,
        "namespace": "openstack",
        "generation": generation,
        "uid": uid or f"uid-{name}",
    }
    if finalizers is not None:
        metadata["finalizers"] = finalizers
    if deletion_timestamp is not None:
        metadata["deletionTimestamp"] = deletion_timestamp

    obj = {
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "metadata": metadata,
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
    """Build one Event context with its associated snapshot."""
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


@pytest.mark.parametrize(
    (
        "scenario",
        "contexts",
        "expected_reconcile",
        "expected_desired",
        "expected_deleted",
        "expected_prune_credentials",
        "expected_unreadable",
    ),
    [
        pytest.param(
            "schedule reconciles every live CR and separates terminating CRs",
            _snapshot_context(
                _cr("b"),
                _cr(
                    "gone",
                    deletion_timestamp="2026-09-14T12:00:00Z",
                    finalizers=[framework.FINALIZER],
                ),
                _cr("a"),
            ),
            ["a", "b"],
            ["a", "b"],
            ["gone"],
            frozenset({("infrasetup", "understack")}),
            frozenset(),
            id="schedule-live-and-terminating",
        ),
        pytest.param(
            "added event reconciles the changed CR but prunes against snapshot",
            [
                _event(
                    "Added",
                    _cr("new", secret="group-a", cloud="cloud-a"),
                    [
                        {"object": _cr("old", secret="group-b", cloud="cloud-b")},
                        {"object": _cr("new", secret="group-a", cloud="cloud-a")},
                    ],
                )
            ],
            ["new"],
            ["new", "old"],
            [],
            frozenset({("group-a", "cloud-a")}),
            frozenset(),
            id="event-reconcile-one-prune-full-snapshot",
        ),
        pytest.param(
            "current status event is ignored and does not trigger prune creds",
            [
                _event(
                    "Modified",
                    _cr(
                        "patched",
                        status={"syncStatus": "Synced", "observedGeneration": 3},
                    ),
                    [{"object": _cr("patched")}],
                )
            ],
            [],
            ["patched"],
            [],
            frozenset(),
            frozenset(),
            id="status-patch-feedback-loop",
        ),
        pytest.param(
            "deleted event prunes with the deleted CR credentials",
            [_event("Deleted", _cr("gone"), [{"object": _cr("kept")}])],
            [],
            ["kept"],
            ["gone"],
            frozenset({("infrasetup", "understack")}),
            frozenset(),
            id="deleted-event-authorizes-prune",
        ),
        pytest.param(
            "deletion timestamp is treated as delete even on modified events",
            [
                _event(
                    "Modified",
                    _cr(
                        "gone",
                        deletion_timestamp="2026-09-14T12:00:00Z",
                        finalizers=[framework.FINALIZER],
                    ),
                    [
                        {
                            "object": _cr(
                                "gone",
                                deletion_timestamp="2026-09-14T12:00:00Z",
                                finalizers=[framework.FINALIZER],
                            )
                        },
                        {"object": _cr("kept")},
                    ],
                )
            ],
            [],
            ["kept"],
            ["gone"],
            frozenset({("infrasetup", "understack")}),
            frozenset(),
            id="modified-with-deletion-timestamp",
        ),
        pytest.param(
            "delete cancels earlier changes for the same CR identity",
            [
                _event("Added", _cr("probe"), []),
                _event("Modified", _cr("probe"), []),
                _event("Deleted", _cr("probe"), []),
            ],
            [],
            [],
            ["probe"],
            frozenset({("infrasetup", "understack")}),
            frozenset(),
            id="same-uid-delete-wins",
        ),
        pytest.param(
            "recreate after delete keeps both logical CRs by UID",
            [
                _event("Deleted", _cr("probe", generation=7, uid="old"), []),
                _event(
                    "Added",
                    _cr("probe", generation=1, uid="new"),
                    [{"object": _cr("probe", generation=1, uid="new")}],
                ),
            ],
            ["probe"],
            ["probe"],
            ["probe"],
            frozenset({("infrasetup", "understack")}),
            frozenset(),
            id="recreate-after-delete",
        ),
        pytest.param(
            "unreadable snapshot keeps desired set incomplete",
            [
                _event(
                    "Deleted",
                    _cr("gone"),
                    [
                        {"object": _cr("kept")},
                        {"object": _cr_without_credentials("legacy")},
                    ],
                )
            ],
            [],
            ["kept"],
            ["gone"],
            frozenset({("infrasetup", "understack")}),
            frozenset({"openstack/legacy"}),
            id="deleted-event-unreadable-snapshot",
        ),
    ],
)
def test_hook_inputs_golden_scenarios(
    scenario,
    contexts,
    expected_reconcile,
    expected_desired,
    expected_deleted,
    expected_prune_credentials,
    expected_unreadable,
):
    config = make_hook_config()

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == (
        expected_reconcile
    ), scenario
    assert [r.spec["name"] for r in inputs.desired_resources_for_prune] == (
        expected_desired
    ), scenario
    assert [
        r.spec["name"] for r in inputs.deleted_resources
    ] == expected_deleted, scenario
    assert inputs.prune_credentials == expected_prune_credentials, scenario
    assert inputs.unreadable_resources == expected_unreadable, scenario


def test_event_batch_ignores_contexts_for_other_bindings():
    """An unrelated binding's snapshot must not drive this hook's prune plan."""
    config = make_hook_config(prune=True)
    stale_other_binding_snapshot = [{"object": _cr("stale-from-other-binding")}]
    live = _cr("live-for-this-binding")
    contexts = [
        {
            "binding": "other-binding",
            "type": "Event",
            "watchEvent": "Modified",
            "object": _cr("ignore-me"),
            "snapshots": {BINDING: stale_other_binding_snapshot},
        },
        _event("Modified", live, [{"object": live}]),
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == [
        "live-for-this-binding"
    ]
    assert [r.spec["name"] for r in inputs.desired_resources_for_prune] == [
        "live-for-this-binding"
    ]


def test_repeated_events_for_one_cr_reconcile_it_once():
    """A failing run can accumulate a backlog; one CR stays one reconcile."""
    config = make_hook_config()
    live = _cr("probe", generation=3)
    contexts = [
        _event("Added", _cr("probe", generation=1), [{"object": live}]),
        _event("Modified", _cr("probe", generation=2), [{"object": live}]),
        _event("Modified", live, [{"object": live}]),
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["probe"]
    assert inputs.resources_to_reconcile[0].generation == 3


def test_collapsed_batch_still_prunes_against_the_whole_snapshot():
    """Collapsing changed events must not narrow the prune desired set."""
    config = make_hook_config(prune=True, status_enabled=True)
    live = _cr("probe", generation=3)
    snapshot = [{"object": live}, {"object": _cr("untouched")}]
    contexts = [_event("Added", _cr("probe", generation=1), snapshot)]
    contexts += [_event("Modified", live, snapshot) for _ in range(2)]

    inputs = hook_inputs(contexts, config)
    plugin = StubPlugin(config)
    code, patch_status, _ = _drive(plugin, inputs)

    assert code == 0
    assert plugin.reconciled == ["probe"]
    assert patch_status.call_count == 1
    assert plugin.pruned == [(["probe", "untouched"], False)]


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


def test_deleted_event_batch_does_not_log_zero_changed_crs(caplog):
    config = make_hook_config()
    contexts = [
        _event("Added", _cr("probe"), []),
        _event("Modified", _cr("probe"), []),
        _event("Deleted", _cr("probe"), []),
    ]

    with caplog.at_level(logging.INFO, logger="openstack_sync.hooks.framework"):
        inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["probe"]
    assert "Collapsed 2 NeutronRouterFlavor changed event(s) across 1 CR(s)" in (
        caplog.text
    )
    assert "into 0 changed CR(s)" not in caplog.text


def test_repeated_delete_events_for_one_cr_are_collapsed():
    config = make_hook_config()
    contexts = [
        _event("Deleted", _cr("probe"), []),
        _event("Deleted", _cr("probe"), []),
    ]

    inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["probe"]


def test_a_recreate_after_a_delete_in_the_same_batch_is_reconciled():
    """UID separates a recreated CR from the object it replaced."""
    config = make_hook_config()
    recreated = _cr("probe", generation=1, uid="new")
    contexts = [
        _event("Deleted", _cr("probe", generation=7, uid="old"), []),
        _event("Added", recreated, [{"object": recreated}]),
    ]

    inputs = hook_inputs(contexts, config)

    assert [r.generation for r in inputs.resources_to_reconcile] == [1]
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["probe"]


def test_a_deleted_cr_does_not_wedge_the_reconcile(caplog):
    """A backlogged deleted CR is pruned once and never status-patched."""
    config = make_hook_config(prune=True, status_enabled=True)

    def gone() -> dict:
        return _cr(
            "zz-probe",
            secret="missing-secret",
            status={"syncStatus": "Failed", "message": "not yet"},
        )

    contexts = [_event("Added", gone(), [])]
    contexts += [_event("Modified", gone(), []) for _ in range(2)]
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

    assert code == 1
    assert plugin.reconciled == []
    assert patch_status.call_count == 0
    assert "Cannot reach OpenStack for widget prune" in caplog.text
    assert "Failed to reconcile" not in caplog.text


def test_deletion_timestamp_reconciles_nothing_but_prunes():
    """A finalizer-protected delete arrives as Modified, not only Deleted."""
    config = make_hook_config()
    gone = _cr(
        "gone",
        finalizers=[framework.FINALIZER],
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Modified",
            "object": gone,
            "snapshots": {BINDING: [{"object": gone}, {"object": _cr("kept")}]},
        }
    ]

    inputs = hook_inputs(contexts, config)

    assert inputs.resources_to_reconcile == []
    assert [r.spec["name"] for r in inputs.desired_resources_for_prune] == ["kept"]
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["gone"]
    assert inputs.deleted_resources[0].has_finalizer is True


def test_snapshot_deletion_timestamp_is_pruned_on_periodic_runs():
    """A restart can recover a delete because the terminating CR remains listed."""
    config = make_hook_config()
    gone = _cr(
        "gone",
        finalizers=[framework.FINALIZER],
        deletion_timestamp="2026-09-14T12:00:00Z",
    )

    inputs = hook_inputs(_snapshot_context(gone, _cr("kept")), config)

    assert [r.spec["name"] for r in inputs.resources_to_reconcile] == ["kept"]
    assert [r.spec["name"] for r in inputs.desired_resources_for_prune] == ["kept"]
    assert [r.spec["name"] for r in inputs.deleted_resources] == ["gone"]
    assert inputs.prune_credentials == frozenset({("infrasetup", "understack")})


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


def test_unreadable_delete_event_is_dropped():
    """A CR that cannot be read cannot be used to drive a deletion either."""
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

    inputs = hook_inputs(contexts, config)

    assert inputs.deleted_resources == []
    assert inputs.unreadable_resources == frozenset({"openstack/legacy"})


def test_deleted_event_with_unreadable_snapshot_skips_prune():
    config = make_hook_config(prune=True)
    contexts = [
        {
            "binding": BINDING,
            "type": "Event",
            "watchEvent": "Deleted",
            "object": _cr("gone"),
            "snapshots": {
                BINDING: [
                    {"object": _cr("kept")},
                    {"object": _cr_without_credentials("legacy")},
                ]
            },
        }
    ]

    inputs = hook_inputs(contexts, config)
    plugin = StubPlugin(config)
    code, _, connect = _drive(plugin, inputs)

    assert [r.spec["name"] for r in inputs.deleted_resources] == ["gone"]
    assert inputs.unreadable_resources == frozenset({"openstack/legacy"})
    assert code == 1
    assert plugin.pruned == []
    connect.assert_not_called()


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
    assert code == 1
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


def test_run_sync_marks_failure_and_skips_prune():
    """A failed reconcile means the desired set is unknown, so prune must not run."""
    plugin = StubPlugin(make_hook_config(prune=True), fail_for=("b",))

    code, patch_status, _ = _drive(plugin, _inputs([_resource("a"), _resource("b")]))

    assert code == 1
    assert plugin.pruned == []
    by_name = {
        call.kwargs["name"]: call.kwargs["sync_status"]
        for call in patch_status.call_args_list
    }
    assert by_name == {"a": "Synced", "b": "Failed"}


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
    assert plugin.pruned == [(["a"], False)]


def test_run_sync_adds_finalizer_before_reconcile_when_prune_enabled():
    plugin = StubPlugin(make_hook_config(prune=True))
    events: list[str] = []

    def add_finalizer(**kwargs):
        events.append("finalizer")
        assert kwargs["finalizer"] == framework.FINALIZER
        assert kwargs["target"].name == "a"
        assert kwargs["target"].kind == CRD_KIND
        assert kwargs["resource_version"] == "12345"
        return True

    def connect(*args):
        events.append("connect")
        return mock.sentinel.conn

    with (
        mock.patch.object(
            framework, "add_resource_finalizer", side_effect=add_finalizer
        ),
        mock.patch.object(framework, "get_openstack_connection", side_effect=connect),
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(framework, "remove_resource_finalizer", return_value=True),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ),
    ):
        code = run_sync(plugin, _inputs([_resource("a", resource_version="12345")]))

    assert code == 0
    assert events == ["finalizer", "connect"]
    assert plugin.reconciled == ["a"]


def test_run_sync_does_not_reconcile_when_finalizer_add_fails():
    plugin = StubPlugin(make_hook_config(prune=True))

    with (
        mock.patch.object(framework, "add_resource_finalizer", return_value=False),
        mock.patch.object(framework, "get_openstack_connection") as connect,
        mock.patch.object(framework, "patch_resource_status") as patch_status,
        mock.patch.object(framework, "remove_resource_finalizer", return_value=True),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ),
    ):
        code = run_sync(plugin, _inputs([_resource("a")]))

    assert code == 1
    connect.assert_not_called()
    assert plugin.reconciled == []
    assert plugin.pruned == []
    assert patch_status.call_args.kwargs["sync_status"] == "Failed"
    assert "finalizer" in patch_status.call_args.kwargs["message"]


def test_run_sync_does_not_add_finalizer_for_base_noop_prune():
    plugin = NoPrunePlugin(make_hook_config(prune=True))

    with (
        mock.patch.object(framework, "add_resource_finalizer") as add,
        mock.patch.object(framework, "get_openstack_connection"),
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(framework, "remove_resource_finalizer", return_value=True),
    ):
        code = run_sync(plugin, _inputs([_resource("a")]))

    assert code == 0
    add.assert_not_called()
    assert plugin.reconciled == ["a"]


def test_run_sync_removes_live_finalizer_when_prune_disabled():
    plugin = StubPlugin(make_hook_config(prune=False))

    with (
        mock.patch.object(framework, "add_resource_finalizer") as add,
        mock.patch.object(framework, "get_openstack_connection") as connect,
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(
            framework, "remove_resource_finalizer", return_value=True
        ) as remove,
    ):
        code = run_sync(
            plugin,
            _inputs([_resource("a", finalizers=(framework.FINALIZER,))]),
        )

    assert code == 0
    add.assert_not_called()
    connect.assert_called_once()
    remove.assert_called_once()
    assert remove.call_args.kwargs["target"].name == "a"
    assert remove.call_args.kwargs["finalizer"] == framework.FINALIZER
    assert plugin.reconciled == ["a"]


def test_run_sync_does_not_run_prune_after_reconcile_when_prune_disabled():
    plugin = StubPlugin(make_hook_config(prune=False))

    code, _, connect = _drive(plugin, _inputs([_resource("a")]))

    assert code == 0
    connect.assert_called_once()
    assert plugin.reconciled == ["a"]
    assert plugin.pruned == []


def test_run_sync_does_not_reconcile_when_disabled_finalizer_remove_fails():
    plugin = StubPlugin(make_hook_config(prune=False))

    with (
        mock.patch.object(framework, "add_resource_finalizer") as add,
        mock.patch.object(framework, "get_openstack_connection") as connect,
        mock.patch.object(framework, "patch_resource_status") as patch_status,
        mock.patch.object(framework, "remove_resource_finalizer", return_value=False),
    ):
        code = run_sync(
            plugin,
            _inputs([_resource("a", finalizers=(framework.FINALIZER,))]),
        )

    assert code == 1
    add.assert_not_called()
    connect.assert_not_called()
    assert plugin.reconciled == []
    assert plugin.pruned == []
    assert patch_status.call_args.kwargs["sync_status"] == "Failed"
    assert "finalizer" in patch_status.call_args.kwargs["message"]


def test_run_sync_prune_is_authoritative_for_deleted_credentials():
    """A confirmed deletion lets prune act on an empty desired set."""
    plugin = StubPlugin(make_hook_config(prune=True))
    deleted = _resource("gone")
    inputs = _inputs([], desired=[], deleted=[deleted])

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    assert plugin.pruned == [([], True)]


def test_run_sync_passes_explicit_prune_request_to_new_api():
    plugin = RequestPrunePlugin(make_hook_config(prune=True))
    deleted = _resource("gone")
    inputs = _inputs([], desired=[], deleted=[deleted])

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    assert plugin.pruned == []
    assert plugin.prune_requests == [
        PruneRequest(
            credentials=("infrasetup", "understack"),
            desired_specs=[],
            authoritative_empty=True,
        )
    ]


def test_run_sync_removes_finalizer_after_successful_prune():
    plugin = StubPlugin(make_hook_config(prune=True))
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([], desired=[], deleted=[deleted])

    with (
        mock.patch.object(framework, "add_resource_finalizer", return_value=True),
        mock.patch.object(framework, "get_openstack_connection"),
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ) as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 0
    assert plugin.pruned == [([], True)]
    release.assert_called_once()
    assert release.call_args.kwargs["target"].name == "gone"
    assert release.call_args.kwargs["finalizer"] == framework.FINALIZER


def test_run_sync_keeps_finalizer_when_prune_fails():
    plugin = StubPlugin(make_hook_config(prune=True), prune_raises=True)
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([], desired=[], deleted=[deleted])

    with (
        mock.patch.object(framework, "add_resource_finalizer", return_value=True),
        mock.patch.object(framework, "get_openstack_connection"),
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(framework, "release_deleted_resource_finalizer") as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 1
    release.assert_not_called()


def test_run_sync_keeps_finalizer_when_deleted_only_prune_cannot_connect():
    plugin = StubPlugin(make_hook_config(prune=True))
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([], desired=[], deleted=[deleted])

    with (
        mock.patch.object(
            framework,
            "get_openstack_connection",
            side_effect=RuntimeError("no route to keystone"),
        ) as connect,
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(framework, "release_deleted_resource_finalizer") as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 1
    connect.assert_called_once_with("infrasetup", "understack")
    assert plugin.pruned == []
    release.assert_not_called()


def test_run_sync_releases_only_successfully_pruned_deleted_credentials():
    plugin = StubPlugin(make_hook_config(prune=True))
    ok = _resource(
        "ok",
        secret="alpha",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    blocked = _resource(
        "blocked",
        secret="broken",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([], desired=[], deleted=[ok, blocked])

    def connect(secret_name: str, cloud_name: str):
        if secret_name == "broken":
            raise RuntimeError("no route to keystone")
        return mock.sentinel.conn

    with (
        mock.patch.object(
            framework, "get_openstack_connection", side_effect=connect
        ) as get_connection,
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ) as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 1
    assert get_connection.call_count == 2
    assert plugin.pruned == [([], True)]
    release.assert_called_once()
    assert release.call_args.kwargs["target"].name == "ok"


def test_run_sync_keeps_finalizer_when_finalized_prune_is_skipped():
    plugin = StubPlugin(make_hook_config(prune=True), fail_for=("bad",))
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([_resource("bad")], desired=[_resource("bad")], deleted=[deleted])

    with (
        mock.patch.object(framework, "add_resource_finalizer", return_value=True),
        mock.patch.object(framework, "get_openstack_connection"),
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(framework, "release_deleted_resource_finalizer") as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 1
    assert plugin.pruned == []
    release.assert_not_called()


def test_run_sync_removes_existing_finalizer_when_prune_disabled():
    plugin = StubPlugin(make_hook_config(prune=False))
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([], desired=[], deleted=[deleted])

    with (
        mock.patch.object(framework, "add_resource_finalizer", return_value=True),
        mock.patch.object(framework, "get_openstack_connection") as connect,
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ) as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 0
    connect.assert_not_called()
    assert plugin.pruned == []
    release.assert_called_once()


def test_run_sync_removes_existing_finalizer_when_prune_disabled_and_reconcile_fails():
    plugin = StubPlugin(make_hook_config(prune=False), fail_for=("bad",))
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([_resource("bad")], desired=[_resource("bad")], deleted=[deleted])

    with (
        mock.patch.object(framework, "get_openstack_connection"),
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ) as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 1
    assert plugin.pruned == []
    release.assert_called_once()
    assert release.call_args.kwargs["target"].name == "gone"


def test_run_sync_removes_existing_finalizer_when_prune_disabled_and_cr_unreadable():
    plugin = StubPlugin(make_hook_config(prune=False))
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs(
        [_resource("a")],
        deleted=[deleted],
        unreadable=frozenset({"openstack/bad"}),
    )

    with (
        mock.patch.object(framework, "get_openstack_connection"),
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ) as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 1
    assert plugin.reconciled == ["a"]
    assert plugin.pruned == []
    release.assert_called_once()
    assert release.call_args.kwargs["target"].name == "gone"


def test_run_sync_removes_existing_finalizer_for_base_noop_prune_without_connection():
    plugin = NoPrunePlugin(make_hook_config(prune=True))
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([], desired=[], deleted=[deleted])

    with (
        mock.patch.object(framework, "add_resource_finalizer") as add,
        mock.patch.object(framework, "get_openstack_connection") as connect,
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ) as release,
    ):
        code = run_sync(plugin, inputs)

    assert code == 0
    add.assert_not_called()
    connect.assert_not_called()
    release.assert_called_once()


def test_run_sync_releases_stale_finalizer_when_best_effort_prune_cannot_connect():
    """A finalizer the plugin no longer uses must not wedge a delete on prune.

    The plugin runs a best-effort sweep even with PRUNE off, but its cleanup
    policy does not use finalizers. When that sweep cannot reach OpenStack the
    run still reports failure, but the stale finalizer is released so the CR can
    finish deleting.
    """
    plugin = AlwaysPrunePlugin(make_hook_config(prune=False))
    deleted = _resource(
        "gone",
        finalizers=(framework.FINALIZER,),
        deletion_timestamp="2026-09-14T12:00:00Z",
    )
    inputs = _inputs([], desired=[], deleted=[deleted])

    with (
        mock.patch.object(
            framework,
            "get_openstack_connection",
            side_effect=RuntimeError("no route to keystone"),
        ),
        mock.patch.object(framework, "patch_resource_status"),
        mock.patch.object(
            framework, "release_deleted_resource_finalizer", return_value=True
        ) as release,
    ):
        code = run_sync(plugin, inputs)

    # The unreachable sweep is still surfaced as a failure...
    assert code == 1
    assert plugin.pruned == []
    # ...but the stale finalizer is released regardless, so the CR is not stuck.
    release.assert_called_once()
    assert release.call_args.kwargs["target"].name == "gone"


def test_run_sync_prunes_against_every_credentials_desired_resources():
    """Prune is scoped by ownership marker, not by credentials, so the set is the union.

    Here the credential whose only CR was deleted has an authoritative empty
    desired set of its own, and can still list what the other credential manages.
    It is handed every group's desired names, which is what keeps the resource
    the other group still wants from being a prune candidate.
    """
    plugin = StubPlugin(make_hook_config(prune=True))
    keeper = _resource("keeper", secret="infrasetup", cloud="understack")
    gone = _resource("gone", secret="infrasetup-system", cloud="understack")
    inputs = _inputs([keeper], desired=[keeper], deleted=[gone])

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    # Sorted by credentials: infrasetup, then infrasetup-system. The second
    # group's desired set is empty and authoritative, and it still sees keeper.
    assert plugin.pruned == [(["keeper"], False), (["keeper"], True)]


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
    inputs = SyncPlan(
        [], [], [], frozenset({("infrasetup", "understack")}), frozenset()
    )

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    assert plugin.pruned == []


def test_run_sync_does_not_connect_for_prune_when_prune_disabled():
    """A deleted-only run must not open a connection just to do nothing."""
    plugin = StubPlugin(make_hook_config(prune=False))
    inputs = _inputs([], desired=[], deleted=[_resource("gone")])

    code, _, connect = _drive(plugin, inputs)

    assert code == 0
    assert connect.call_count == 0
    assert plugin.pruned == []


def test_run_sync_returns_error_when_prune_fails():
    plugin = StubPlugin(make_hook_config(prune=True), prune_raises=True)

    code, _, _ = _drive(plugin, _inputs([_resource("a")]))

    assert code == 1


def test_run_sync_skips_prune_when_a_cr_was_unreadable():
    plugin = StubPlugin(make_hook_config(prune=True))
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

    # Non-zero keeps the problem visible, but the healthy CRs still converge and
    # still get their status patched.
    assert code == 1
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
