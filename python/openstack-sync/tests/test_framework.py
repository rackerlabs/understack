"""Tests for the generic sync framework.

Deliberately free of Neutron: the driver is exercised through a stub plugin, so
these tests describe the contract any future plugin can rely on.
"""

from __future__ import annotations

import json
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


def _cr(name: str, generation: int = 3, status: dict | None = None) -> dict:
    obj = {
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "metadata": {"name": name, "namespace": "openstack", "generation": generation},
        "spec": {
            "name": name,
            "cloudCredentialsRef": {
                "secretName": "infrasetup",
                "cloudName": "understack",
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
#
# A CRD's required fields bind writes only. Kubernetes validates on admission,
# so an object stored before the schema required a field is still served by the
# watch exactly as stored, and admission is no guarantee about what a hook
# reads. The contract: name the offending CR, drop it, reconcile the rest, and
# never prune against the resulting incomplete desired set.
# ---------------------------------------------------------------------------


def _cr_without_credentials(name: str, generation: int = 1) -> dict:
    """A CR stored before the CRD required spec.cloudCredentialsRef."""
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
    """One malformed CR must not take down the whole batch."""
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
    """minLength: 1 in the CRD does not constrain what is already stored."""
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
    """Enabling a hook on a namespace that predates the CRD's required fields.

    The mixture that matters: several CRs stored under the older schema
    alongside conforming ones. The conforming CRs must converge, the run must
    still report failure, and prune must not act on the partial desired set.
    """
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

    The CRD identity targets kubectl, and the current status decides whether the
    patch can be skipped.
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


def test_run_sync_prune_is_authoritative_for_deleted_credentials():
    """A confirmed deletion lets prune act on an empty desired set."""
    plugin = StubPlugin(make_hook_config(prune=True))
    deleted = _resource("gone")
    inputs = _inputs([], desired=[], deleted=[deleted])

    code, _, _ = _drive(plugin, inputs)

    assert code == 0
    assert plugin.pruned == [([], True)]


def test_run_sync_skips_prune_for_credentials_with_no_desired_resources():
    """An empty desired set with no deletion may be an unreadable snapshot."""
    plugin = StubPlugin(make_hook_config(prune=True))
    inputs = HookInputs(
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
    """An unreadable CR is missing from the desired set.

    Pruning against that set would delete the resource the unreadable CR still
    describes, the same hazard as pruning after a failed reconcile.
    """
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
