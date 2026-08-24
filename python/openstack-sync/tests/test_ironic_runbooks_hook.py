"""Tests for the Ironic runbook hook wiring.

The hook registers the right CRD watch, delegates reconcile and prune to the
plugin package, and processes CRs through the shared framework. What each
delegate does is covered in ``test_ironic_runbooks_reconcile.py`` and
``test_ironic_runbooks_prune.py``.
"""

from __future__ import annotations

import importlib
import json
import types
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from openstack_sync.hooks import ironic_runbooks as hook
from openstack_sync.hooks.framework import HookConfig
from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.ironic.runbooks import markers
from openstack_sync.plugins.ironic.runbooks.config import BINDING_NAME
from openstack_sync.plugins.ironic.runbooks.config import ENV_PREFIX
from openstack_sync.plugins.ironic.runbooks.config import RUNBOOK_MICROVERSION
from tests.test_ironic_runbooks_reconcile import FakeBaremetal

CRD_API_VERSION = "baremetal.ironicproject.org/v1alpha1"
CRD_KIND = "IronicRunbook"
CRD_RESOURCE = "ironicrunbooks.baremetal.ironicproject.org"

RUNBOOK_NAME = "firmware-r740xd"

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


def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def set_crd_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(f"{ENV_PREFIX}_CRD_API_VERSION", CRD_API_VERSION)
    monkeypatch.setenv(f"{ENV_PREFIX}_CRD_KIND", CRD_KIND)
    monkeypatch.setenv(f"{ENV_PREFIX}_CRD_RESOURCE", CRD_RESOURCE)


def make_ironic_config(**overrides: Any) -> HookConfig:
    defaults = {
        "prefix": ENV_PREFIX,
        "crd_api_version": CRD_API_VERSION,
        "crd_kind": CRD_KIND,
        "crd_resource": CRD_RESOURCE,
        "binding_name": BINDING_NAME,
        "namespace": "openstack",
        "status_enabled": True,
        "prune": False,
        "sync_crontab": "",
        "ready_retries": 30,
        "ready_delay": 10.0,
    }
    return HookConfig(**{**defaults, **overrides})


def ironic_runbook_object(name: str, spec: dict[str, Any] | None = None) -> dict:
    runbook_spec: dict[str, Any] = {
        "cloudCredentialsRef": {
            "secretName": "infrasetup",
            "cloudName": "understack",
        },
        "runbookName": name,
        "description": f"{name} description",
        "public": True,
        "traits": ["CUSTOM_DELL_POWEREDGE_R740XD"],
        "steps": [
            {
                "interface": "firmware",
                "step": "update",
                "args": {"settings": [{"component": "bios", "wait": 1200}]},
                "order": 1,
            }
        ],
    }
    runbook_spec.update(spec or {})
    return {
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "metadata": {"name": name, "namespace": "openstack", "generation": 3},
        "spec": runbook_spec,
    }


def write_binding_context(path: Path, contexts: list[dict[str, Any]]) -> str:
    context_path = path / "binding-context.json"
    context_path.write_text(json.dumps(contexts), encoding="utf-8")
    return str(context_path)


def schedule_context(*names: str) -> list[dict[str, Any]]:
    return [
        {
            "binding": BINDING_NAME,
            "type": "Schedule",
            "snapshots": {
                BINDING_NAME: [{"object": ironic_runbook_object(n)} for n in names]
            },
        }
    ]


def test_module_import_is_safe_with_bad_runtime_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(f"{ENV_PREFIX}_READY_RETRIES", "not-a-number")
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "not-a-bool")

    importlib.reload(hook)


def test_config_flag_prints_disabled_startup_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    clear_env(monkeypatch)
    monkeypatch.setattr(hook.sys, "argv", ["ironic_runbooks.py", "--config"])

    assert hook.main() == 0
    assert json.loads(capsys.readouterr().out)["onStartup"] == 10


def test_enabled_config_flag_watches_ironic_runbook_crd(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setattr(hook.sys, "argv", ["ironic_runbooks.py", "--config"])

    assert hook.main() == 0
    config = json.loads(capsys.readouterr().out)
    (binding,) = config["kubernetes"]
    assert binding["name"] == BINDING_NAME
    assert binding["apiVersion"] == CRD_API_VERSION
    assert binding["kind"] == CRD_KIND
    assert binding["namespace"] == {"nameSelector": {"matchNames": ["openstack"]}}
    assert "schedule" not in config


def test_enabled_config_flag_adds_schedule_when_configured(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_SYNC_CRONTAB", "*/10 * * * *")
    monkeypatch.setattr(hook.sys, "argv", ["ironic_runbooks.py", "--config"])

    assert hook.main() == 0
    config = json.loads(capsys.readouterr().out)
    (schedule,) = config["schedule"]
    assert schedule["crontab"] == "*/10 * * * *"
    assert schedule["includeSnapshotsFrom"] == [BINDING_NAME]
    assert schedule["queue"] == BINDING_NAME


def test_plugin_reconcile_delegates_to_sync_runbook():
    plugin = hook.IronicRunbookPlugin(make_ironic_config())
    conn = mock.MagicMock()
    cache: dict[str, Any] = {}
    spec = {"runbookName": "CUSTOM_BIOS_R740XD", "steps": []}

    with mock.patch.object(
        hook.reconcile_module, "sync_runbook", return_value=["a note"]
    ) as sync_runbook:
        notes = plugin.reconcile(conn, spec, cache)

    assert notes == ["a note"]
    sync_runbook.assert_called_once_with(conn, spec, cache)


def test_plugin_waits_for_the_runbook_api_with_the_configured_budget():
    plugin = hook.IronicRunbookPlugin(
        make_ironic_config(ready_retries=5, ready_delay=2)
    )
    conn = mock.MagicMock()

    with mock.patch.object(hook.client, "wait_for_runbook_api") as wait:
        plugin.wait_for_api(conn)

    wait.assert_called_once_with(conn, retries=5, delay=2)


def test_plugin_prunes_only_when_the_chart_enabled_it():
    """PRUNE is opt-in: deleting a runbook is not undone by re-adding the CR."""
    conn = mock.MagicMock()
    specs = [{"runbookName": "CUSTOM_KEEP", "steps": []}]

    with mock.patch.object(hook.prune_module, "prune_removed_runbooks") as do_prune:
        hook.IronicRunbookPlugin(make_ironic_config(prune=False)).prune(
            conn, specs, authoritative_empty=False
        )
        do_prune.assert_not_called()

        hook.IronicRunbookPlugin(make_ironic_config(prune=True)).prune(
            conn, specs, authoritative_empty=True
        )
        do_prune.assert_called_once_with(conn, specs, authoritative_empty=True)


def test_main_returns_zero_when_hook_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH",
        write_binding_context(tmp_path, schedule_context(RUNBOOK_NAME)),
    )

    with (
        mock.patch.object(hook.sys, "argv", ["ironic_runbooks.py"]),
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection"
        ) as connect,
        mock.patch("openstack_sync.hooks.framework.patch_resource_status") as status,
    ):
        assert hook.main() == 0

    connect.assert_not_called()
    status.assert_not_called()


def test_main_reconciles_the_runbook_and_reports_synced(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_STATUS_ENABLED", "true")
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH",
        write_binding_context(tmp_path, schedule_context(RUNBOOK_NAME)),
    )

    with (
        mock.patch.object(hook.sys, "argv", ["ironic_runbooks.py"]),
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection",
            return_value=mock.MagicMock(),
        ) as connect,
        mock.patch("openstack_sync.hooks.framework.patch_resource_status") as status,
        mock.patch.object(hook.client, "wait_for_runbook_api"),
        mock.patch.object(
            hook.reconcile_module, "sync_runbook", return_value=[]
        ) as sync_runbook,
    ):
        assert hook.main() == 0

    connect.assert_called_once_with("infrasetup", "understack")
    assert sync_runbook.call_args.args[1]["runbookName"] == RUNBOOK_NAME
    assert status.call_args.kwargs["sync_status"] == "Synced"
    assert status.call_args.kwargs["crd_kind"] == CRD_KIND
    assert status.call_args.kwargs["crd_resource"] == CRD_RESOURCE
    assert (
        status.call_args.kwargs["message"] == "Successfully reconciled ironic runbook"
    )


def test_main_reports_failed_when_the_runbook_cannot_be_reconciled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_STATUS_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_PRUNE", "true")
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH",
        write_binding_context(tmp_path, schedule_context(RUNBOOK_NAME)),
    )

    with (
        mock.patch.object(hook.sys, "argv", ["ironic_runbooks.py"]),
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection",
            return_value=mock.MagicMock(),
        ),
        mock.patch("openstack_sync.hooks.framework.patch_resource_status") as status,
        mock.patch.object(hook.client, "wait_for_runbook_api"),
        mock.patch.object(
            hook.reconcile_module,
            "sync_runbook",
            side_effect=ConfigError("steps must be a non-empty list"),
        ),
        mock.patch.object(hook.prune_module, "prune_removed_runbooks") as do_prune,
    ):
        assert hook.main() == 1

    assert status.call_args.kwargs["sync_status"] == "Failed"
    assert status.call_args.kwargs["message"] == "steps must be a non-empty list"
    # The desired set is unknown once a CR failed, so nothing may be deleted.
    do_prune.assert_not_called()


# ---------------------------------------------------------------------------
# End to end
# ---------------------------------------------------------------------------


def test_main_creates_then_prunes_against_a_fake_ironic(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """One pass through the whole chain with nothing below the hook mocked.

    Binding context -> framework -> reconcile -> runbook client -> Ironic routes,
    then the same for prune once the CR is gone. Only the connection, the
    microversion discovery and kubectl are stood in for.
    """
    fake = FakeBaremetal()
    conn = types.SimpleNamespace(baremetal=fake)

    def run(contexts: list[dict[str, Any]], prune: str) -> int:
        monkeypatch.setenv(
            "BINDING_CONTEXT_PATH", write_binding_context(tmp_path, contexts)
        )
        monkeypatch.setenv(f"{ENV_PREFIX}_PRUNE", prune)
        with (
            mock.patch.object(hook.sys, "argv", ["ironic_runbooks.py"]),
            mock.patch(
                "openstack_sync.hooks.framework.get_openstack_connection",
                return_value=conn,
            ),
            mock.patch("openstack_sync.hooks.framework.patch_resource_status"),
            mock.patch.object(
                hook.client.openstack_utils,
                "maximum_supported_microversion",
                return_value=RUNBOOK_MICROVERSION,
            ),
        ):
            return hook.main()

    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")

    assert run(schedule_context(RUNBOOK_NAME), "false") == 0
    created = fake.runbooks[RUNBOOK_NAME]
    assert created["steps"][0]["args"] == {
        "settings": [{"component": "bios", "wait": 1200}]
    }
    assert created["description"] == f"{RUNBOOK_NAME} description"
    assert created["traits"] == ["CUSTOM_DELL_POWEREDGE_R740XD"]
    assert markers.is_managed_runbook(created)

    # A second pass over an unchanged CR must not write anything.
    fake.calls.clear()
    assert run(schedule_context(RUNBOOK_NAME), "false") == 0
    assert fake.calls_for("PATCH") == []
    assert fake.calls_for("POST") == []
    assert fake.calls_for("PUT") == []

    # The CR is deleted: with PRUNE on, the runbook goes with it.
    deleted = [
        {
            "binding": BINDING_NAME,
            "type": "Event",
            "watchEvent": "Deleted",
            "object": ironic_runbook_object(RUNBOOK_NAME),
            "snapshots": {BINDING_NAME: []},
        }
    ]
    assert run(deleted, "true") == 0
    assert fake.runbooks == {}
