"""Tests for the segment range hook: how the plugin wires into the framework.

The generic driver is covered in ``test_framework.py``; these tests cover only
what is specific to this plugin, plus end-to-end runs through ``main()`` and
``run_sync()``. Spec validation and immutable-drift logic live in
``test_segment_ranges_reconcile.py``.
"""

from __future__ import annotations

import importlib
import json
import types
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

import openstack_sync.utils as utils
from openstack_sync.hooks import segment_ranges as hook
from openstack_sync.hooks.framework import CleanupPolicy
from openstack_sync.hooks.framework import HookConfig
from openstack_sync.hooks.framework import ReconcileResult
from openstack_sync.hooks.framework import SyncPlan
from openstack_sync.hooks.framework import SyncResource
from openstack_sync.plugins.neutron.segment_ranges.config import BINDING_NAME
from openstack_sync.plugins.neutron.segment_ranges.config import ENV_PREFIX

CRD_API_VERSION = "neutron.understack.rackspace.net/v1alpha1"
CRD_KIND = "NeutronSegmentRange"
CRD_RESOURCE = "neutronsegmentranges.neutron.understack.rackspace.net"

ENV_NAMES = (
    "BINDING_CONTEXT_PATH",
    f"{ENV_PREFIX}_ENABLED",
    f"{ENV_PREFIX}_SYNC_CRONTAB",
    f"{ENV_PREFIX}_PRUNE",
    f"{ENV_PREFIX}_STATUS_ENABLED",
    f"{ENV_PREFIX}_READY_RETRIES",
    f"{ENV_PREFIX}_READY_DELAY",
    f"{ENV_PREFIX}_CRD_API_VERSION",
    f"{ENV_PREFIX}_CRD_KIND",
    f"{ENV_PREFIX}_CRD_RESOURCE",
    "POD_NAMESPACE",
)


def _config(**overrides: Any) -> HookConfig:
    defaults = {
        "prefix": ENV_PREFIX,
        "crd_api_version": CRD_API_VERSION,
        "crd_kind": CRD_KIND,
        "crd_resource": CRD_RESOURCE,
        "binding_name": BINDING_NAME,
        "namespace": "openstack",
        "status_enabled": False,
        "prune": False,
        "sync_crontab": "",
        "ready_retries": 30,
        "ready_delay": 10.0,
    }
    return HookConfig(**{**defaults, **overrides})


def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def set_crd_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}_CRD_API_VERSION", CRD_API_VERSION)
    monkeypatch.setenv(f"{ENV_PREFIX}_CRD_KIND", CRD_KIND)
    monkeypatch.setenv(f"{ENV_PREFIX}_CRD_RESOURCE", CRD_RESOURCE)


def segment_range_object(name: str, spec: dict | None = None) -> dict:
    range_spec: dict[str, Any] = {
        "name": name,
        "network_type": "vlan",
        "physical_network": "physnet1",
        "minimum": 100,
        "maximum": 200,
        "shared": True,
        "cloudCredentialsRef": {
            "secretName": "infrasetup",
            "cloudName": "understack",
        },
    }
    range_spec.update(spec or {})
    return {
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "metadata": {"name": name, "namespace": "openstack", "generation": 3},
        "spec": range_spec,
    }


def write_binding_context(path: Path, contexts: list[dict]) -> str:
    context_path = path / "binding-context.json"
    context_path.write_text(json.dumps(contexts), encoding="utf-8")
    return str(context_path)


def _range(name: str, **overrides: Any) -> types.SimpleNamespace:
    """A Neutron range named exactly as the CR declares it (no prefix)."""
    attrs: dict[str, Any] = {
        "id": f"{name}-id",
        "name": name,
        "network_type": "vlan",
        "physical_network": "physnet1",
        "minimum": 100,
        "maximum": 200,
        "shared": True,
        "project_id": None,
    }
    attrs.update(overrides)
    return types.SimpleNamespace(**attrs)


def _neutron_conn(ranges: list[Any] | None = None) -> Any:
    conn = mock.MagicMock()
    conn.network.network_segment_ranges.return_value = list(
        ranges if ranges is not None else [_range("vlan-a")]
    )
    return conn


# ---------------------------------------------------------------------------
# Import safety
# ---------------------------------------------------------------------------


def test_module_import_is_safe_with_bad_runtime_env(monkeypatch):
    """Importing must not read runtime config."""
    monkeypatch.setenv(f"{ENV_PREFIX}_READY_RETRIES", "not-a-number")
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "not-a-bool")

    importlib.reload(hook)


def test_enabled_config_flag_watches_this_crd(monkeypatch, capsys):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setattr(hook.sys, "argv", ["segment_ranges.py", "--config"])

    assert hook.main() == 0
    config = json.loads(capsys.readouterr().out)
    (binding,) = config["kubernetes"]
    assert binding["name"] == BINDING_NAME
    assert binding["kind"] == CRD_KIND


# ---------------------------------------------------------------------------
# Plugin wiring
# ---------------------------------------------------------------------------


def test_plugin_reconcile_wraps_notes_in_reconcile_result():
    """reconcile() must return a ReconcileResult, not the bare note list.

    The framework reads ``result.notes`` outside the reconcile try/except, so a
    plain list would raise AttributeError on the first clean sync.
    """
    plugin = hook.SegmentRangePlugin(_config())
    conn = mock.MagicMock()
    cache: dict[str, Any] = {}
    spec = {"name": "vlan-a"}

    with mock.patch.object(
        hook.reconcile_module, "sync_segment_range", return_value=["a note"]
    ) as sync_range:
        result = plugin.reconcile(conn, spec, cache)

    assert isinstance(result, ReconcileResult)
    assert result.notes == ["a note"]
    sync_range.assert_called_once_with(conn, spec, cache)


def test_plugin_wait_for_api_uses_configured_retry_budget():
    plugin = hook.SegmentRangePlugin(_config(ready_retries=5, ready_delay=0.25))
    conn = mock.MagicMock()

    with mock.patch.object(hook, "wait_for_openstack_network") as wait:
        plugin.wait_for_api(conn)

    wait.assert_called_once_with(conn, retries=5, delay=0.25)


# ---------------------------------------------------------------------------
# Cleanup policy: a segment range outlives its CR, so the plugin never prunes
# ---------------------------------------------------------------------------


def test_plugin_never_prunes_even_when_prune_flag_is_set():
    """A segment range is never deleted by the operator.

    The plugin defines no prune step, so the framework's cleanup policy is NONE
    regardless of the chart's prune flag: no prune pass, no finalizer.
    """
    plugin = hook.SegmentRangePlugin(_config(prune=True))

    assert plugin.cleanup_policy() is CleanupPolicy.NONE
    assert plugin.should_run_prune() is False
    assert plugin.uses_finalizer() is False


def test_plugin_cleanup_policy_is_none_when_prune_disabled():
    plugin = hook.SegmentRangePlugin(_config(prune=False))

    assert plugin.cleanup_policy() is CleanupPolicy.NONE
    assert plugin.should_run_prune() is False
    assert plugin.uses_finalizer() is False


# ---------------------------------------------------------------------------
# Integration through run_sync(): the ReconcileResult contract end to end
# ---------------------------------------------------------------------------


def test_run_sync_reports_synced_for_a_clean_reconcile():
    """A clean sync must go through run_sync without an AttributeError.

    This is the regression guard for the ReconcileResult contract: the driver
    reads ``result.notes`` after the reconcile call returns.
    """
    plugin = hook.SegmentRangePlugin(_config(status_enabled=True))
    resource = SyncResource(
        spec={
            "name": "vlan-a",
            "network_type": "vlan",
            "physical_network": "physnet1",
            "minimum": 100,
            "maximum": 200,
            "shared": True,
        },
        name="vlan-a",
        namespace="openstack",
        generation=3,
        secret_name="infrasetup",
        cloud_name="understack",
    )
    conn = _neutron_conn([_range("vlan-a")])
    inputs = SyncPlan(
        resources_to_reconcile=[resource],
        desired_resources_for_prune=[resource],
        deleted_resources=[],
        prune_credentials=frozenset(),
        unreadable_resources=frozenset(),
    )

    with (
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection",
            return_value=conn,
        ),
        mock.patch(
            "openstack_sync.hooks.framework.patch_resource_status"
        ) as patch_status,
        mock.patch.object(hook, "wait_for_openstack_network"),
    ):
        code = hook.run_sync(plugin, inputs)

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    # Already converged: no writes to Neutron.
    conn.network.create_network_segment_range.assert_not_called()
    conn.network.update_network_segment_range.assert_not_called()


# ---------------------------------------------------------------------------
# End to end through main()
# ---------------------------------------------------------------------------


def _run_main(monkeypatch, tmp_path, contexts: list[dict], conn: Any):
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH", write_binding_context(tmp_path, contexts)
    )
    with (
        mock.patch.object(hook.sys, "argv", ["segment_ranges.py"]),
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection",
            return_value=conn,
        ),
        mock.patch(
            "openstack_sync.hooks.framework.patch_resource_status"
        ) as patch_status,
        mock.patch(
            "openstack_sync.hooks.framework.add_resource_finalizer",
            return_value=True,
        ),
        mock.patch(
            "openstack_sync.hooks.framework.remove_resource_finalizer",
            return_value=True,
        ),
        mock.patch.object(hook, "wait_for_openstack_network"),
    ):
        code = hook.main()
    return code, patch_status


def _schedule_context(*names: str) -> list[dict]:
    return [
        {
            "binding": BINDING_NAME,
            "type": "Schedule",
            "snapshots": {
                BINDING_NAME: [{"object": segment_range_object(n)} for n in names]
            },
        }
    ]


def test_main_returns_zero_when_hook_disabled(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    conn = _neutron_conn()

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("vlan-a"), conn
    )

    assert code == 0
    patch_status.assert_not_called()
    conn.network.network_segment_ranges.assert_not_called()


def test_main_reconciles_an_already_converged_range(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    conn = _neutron_conn([_range("vlan-a")])

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("vlan-a"), conn
    )

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    conn.network.create_network_segment_range.assert_not_called()
    conn.network.update_network_segment_range.assert_not_called()


def test_main_creates_a_missing_range_with_the_declared_name(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    conn = _neutron_conn([])
    conn.network.create_network_segment_range.return_value = _range("vlan-a")

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("vlan-a"), conn
    )

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    create_kwargs = conn.network.create_network_segment_range.call_args.kwargs
    # The CR's logical name is the real Neutron name; no owner prefix.
    assert create_kwargs["name"] == "vlan-a"


def test_main_adopts_a_range_created_out_of_band(monkeypatch, tmp_path):
    """A range with the CR's name but divergent minimum is adopted and updated.

    No ownership marker gates adoption: the plugin matches an existing range by
    its name.
    """
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    existing = _range("vlan-a", minimum=50)
    conn = _neutron_conn([existing])
    conn.network.update_network_segment_range.return_value = _range("vlan-a")

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("vlan-a"), conn
    )

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    conn.network.create_network_segment_range.assert_not_called()
    update_kwargs = conn.network.update_network_segment_range.call_args.kwargs
    assert update_kwargs == {"minimum": 100}


def test_main_fails_when_immutable_field_diverges(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    # Existing range differs on physical_network, which Neutron cannot update.
    conn = _neutron_conn([_range("vlan-a", physical_network="physnet2")])

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("vlan-a"), conn
    )

    assert code == 1
    assert patch_status.call_args.kwargs["sync_status"] == "Failed"
    assert "physical_network" in patch_status.call_args.kwargs["message"]


def test_main_never_deletes_a_range_when_its_cr_is_absent(monkeypatch, tmp_path):
    """A managed range with no surviving CR is left in place, not pruned.

    Even with the prune flag set, the plugin defines no prune step, so a range
    whose CR was removed survives for an operator to drain and delete.
    """
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_PRUNE", "true")
    # Neutron holds a stale range; only vlan-a has a CR in the snapshot.
    conn = _neutron_conn([_range("vlan-a"), _range("vlan-stale", id="stale-id")])

    code, _ = _run_main(monkeypatch, tmp_path, _schedule_context("vlan-a"), conn)

    assert code == 0
    conn.network.delete_network_segment_range.assert_not_called()


def test_main_uses_the_credentials_named_by_each_cr(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setattr(utils, "_connection_cache", {})
    contexts = _schedule_context("vlan-a")
    contexts[0]["snapshots"][BINDING_NAME][0]["object"]["spec"][
        "cloudCredentialsRef"
    ] = {"secretName": "other-secret", "cloudName": "other-cloud"}
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH", write_binding_context(tmp_path, contexts)
    )

    with (
        mock.patch.object(hook.sys, "argv", ["segment_ranges.py"]),
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection",
            return_value=_neutron_conn([_range("vlan-a")]),
        ) as connect,
        mock.patch("openstack_sync.hooks.framework.patch_resource_status"),
        mock.patch.object(hook, "wait_for_openstack_network"),
    ):
        assert hook.main() == 0

    connect.assert_called_once_with("other-secret", "other-cloud")
