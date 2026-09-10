"""Tests for the router flavor hook: how the plugin wires into the framework.

The generic driver is covered in ``test_framework.py``; these tests cover only
what is specific to this plugin, plus one end-to-end run through ``main()``.
"""

from __future__ import annotations

import importlib
import json
import logging
import types
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

import openstack_sync.utils as utils
from openstack_sync.hooks import router_flavors as hook
from openstack_sync.plugins.neutron.router_flavors import markers
from openstack_sync.plugins.neutron.router_flavors.config import BINDING_NAME
from openstack_sync.plugins.neutron.router_flavors.config import ENV_PREFIX
from openstack_sync.plugins.neutron.router_flavors.config import SERVICE_TYPE
from tests.conftest import CRD_API_VERSION
from tests.conftest import CRD_KIND
from tests.conftest import make_hook_config

ENV_NAMES = (
    "BINDING_CONTEXT_PATH",
    f"{ENV_PREFIX}_ENABLED",
    f"{ENV_PREFIX}_SYNC_CRONTAB",
    f"{ENV_PREFIX}_PRUNE",
    f"{ENV_PREFIX}_STATUS_ENABLED",
    f"{ENV_PREFIX}_READY_RETRIES",
    f"{ENV_PREFIX}_READY_DELAY",
    "POD_NAMESPACE",
)

FAKE_CLOUDS_YAML = """
clouds:
  understack:
    auth:
      auth_url: https://keystone.example.com/v3
      username: infrasetup
      password: secret
      project_name: baremetal
    region_name: iad3
"""


def clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def router_flavor_object(name: str, spec: dict | None = None) -> dict:
    flavor_spec: dict[str, Any] = {
        "name": name,
        "service_type": SERVICE_TYPE,
        "description": f"{name} description",
        "is_enabled": True,
        "service_profiles": [
            {
                "driver": "neutron_understack.l3_router.vrf.Vrf",
                "description": f"{name} profile",
                "meta_info": {"vni_alloc": "auto"},
                "is_enabled": True,
            }
        ],
        "cloudCredentialsRef": {
            "secretName": "infrasetup",
            "cloudName": "understack",
        },
    }
    flavor_spec.update(spec or {})
    return {
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "metadata": {"name": name, "namespace": "openstack", "generation": 3},
        "spec": flavor_spec,
    }


def write_binding_context(path: Path, contexts: list[dict]) -> str:
    context_path = path / "binding-context.json"
    context_path.write_text(json.dumps(contexts), encoding="utf-8")
    return str(context_path)


# ---------------------------------------------------------------------------
# Import safety
# ---------------------------------------------------------------------------


def test_module_import_is_safe_with_bad_runtime_env(monkeypatch):
    """Importing must not read runtime config.

    Shell-operator imports the hook to ask for its config before the full
    environment is guaranteed, so a malformed value must not break import.
    """
    monkeypatch.setenv(f"{ENV_PREFIX}_READY_RETRIES", "not-a-number")
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "not-a-bool")

    importlib.reload(hook)


def test_config_flag_prints_json(monkeypatch, capsys):
    clear_env(monkeypatch)
    monkeypatch.setattr(hook.sys, "argv", ["router_flavors.py", "--config"])

    assert hook.main() == 0
    assert json.loads(capsys.readouterr().out)["onStartup"] == 10


def test_enabled_config_flag_watches_this_crd(monkeypatch, capsys):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setattr(hook.sys, "argv", ["router_flavors.py", "--config"])

    assert hook.main() == 0
    config = json.loads(capsys.readouterr().out)
    (binding,) = config["kubernetes"]
    assert binding["name"] == BINDING_NAME
    assert binding["kind"] == CRD_KIND


# ---------------------------------------------------------------------------
# Plugin wiring
# ---------------------------------------------------------------------------


def test_plugin_reconcile_delegates_to_sync_flavor():
    plugin = hook.RouterFlavorPlugin(make_hook_config())
    conn = mock.MagicMock()
    cache: dict[str, Any] = {}
    spec = {"name": "flavor-a"}

    with mock.patch.object(
        hook.reconcile_module, "sync_flavor", return_value=["a note"]
    ) as sync_flavor:
        notes = plugin.reconcile(conn, spec, cache)

    assert notes == ["a note"]
    sync_flavor.assert_called_once_with(conn, spec, cache)


def test_plugin_wait_for_api_uses_configured_retry_budget():
    plugin = hook.RouterFlavorPlugin(
        make_hook_config(ready_retries=5, ready_delay=0.25)
    )
    conn = mock.MagicMock()

    with mock.patch.object(hook, "wait_for_openstack_network") as wait:
        plugin.wait_for_api(conn)

    wait.assert_called_once_with(conn, retries=5, delay=0.25)


def test_plugin_prune_deletes_no_flavor_when_disabled():
    plugin = hook.RouterFlavorPlugin(make_hook_config(prune=False))

    with mock.patch.object(hook.prune_module, "prune_removed_flavors") as prune:
        plugin.prune(
            mock.MagicMock(), [{"name": "a"}], deleted_specs=[], sweep_unseen=True
        )

    prune.assert_not_called()


def test_plugin_prune_sweeps_orphaned_profiles_when_disabled():
    """PRUNE gates flavor deletion; an unattached owned profile is collected anyway."""
    plugin = hook.RouterFlavorPlugin(make_hook_config(prune=False))
    conn = mock.MagicMock()

    with mock.patch.object(hook.prune_module, "prune_orphaned_profiles") as sweep:
        plugin.prune(conn, [{"name": "a"}], deleted_specs=[], sweep_unseen=True)

    sweep.assert_called_once_with(conn)


def test_plugin_prune_ignores_a_deletion_when_disabled():
    """PRUNE off means a lost CR's flavor is left in place, not deleted by name."""
    plugin = hook.RouterFlavorPlugin(make_hook_config(prune=False))
    conn = mock.MagicMock()

    with (
        mock.patch.object(hook.prune_module, "prune_removed_flavors") as prune,
        mock.patch.object(hook.prune_module, "prune_orphaned_profiles") as sweep,
    ):
        plugin.prune(conn, [], deleted_specs=[{"name": "gone"}], sweep_unseen=True)

    prune.assert_not_called()
    sweep.assert_called_once_with(conn)


def test_plugin_prune_forwards_deleted_specs_when_enabled():
    plugin = hook.RouterFlavorPlugin(make_hook_config(prune=True))
    conn = mock.MagicMock()
    specs = [{"name": "a"}]
    deleted = [{"name": "gone"}]

    with (
        mock.patch.object(hook.prune_module, "prune_removed_flavors") as prune,
        mock.patch.object(hook.prune_module, "prune_orphaned_profiles") as sweep,
    ):
        plugin.prune(conn, specs, deleted_specs=deleted, sweep_unseen=True)

    prune.assert_called_once_with(conn, specs, deleted_specs=deleted, sweep_unseen=True)
    # prune_removed_flavors sweeps internally; a second call would re-list.
    sweep.assert_not_called()


def test_plugin_prune_forwards_a_withheld_sweep():
    """The framework's decision not to delete by absence must reach the module."""
    plugin = hook.RouterFlavorPlugin(make_hook_config(prune=True))
    conn = mock.MagicMock()
    specs = [{"name": "a"}]
    deleted = [{"name": "gone"}]

    with mock.patch.object(hook.prune_module, "prune_removed_flavors") as prune:
        plugin.prune(conn, specs, deleted_specs=deleted, sweep_unseen=False)

    prune.assert_called_once_with(
        conn, specs, deleted_specs=deleted, sweep_unseen=False
    )


def test_plugin_cache_is_per_credential_group():
    plugin = hook.RouterFlavorPlugin(make_hook_config())

    assert plugin.new_cache() == {}
    assert plugin.new_cache() is not plugin.new_cache()


# ---------------------------------------------------------------------------
# End to end through main()
# ---------------------------------------------------------------------------


def _neutron_conn() -> Any:
    """A Neutron connection that already holds the desired flavor and profile."""
    profile = types.SimpleNamespace(
        id="profile-id",
        driver="neutron_understack.l3_router.vrf.Vrf",
        is_enabled=True,
        description="pa1410 profile",
        meta_info=markers.managed_meta_info({"vni_alloc": "auto"}),
    )
    flavor = types.SimpleNamespace(
        id="flavor-id",
        name="pa1410",
        service_type=SERVICE_TYPE,
        description=markers.managed_flavor_description("pa1410 description"),
        is_enabled=True,
        service_profile_ids=["profile-id"],
    )
    conn = mock.MagicMock()
    conn.network.service_profiles.return_value = [profile]
    conn.network.flavors.return_value = [flavor]
    conn.network.get_flavor.return_value = flavor
    return conn


def _run_main(monkeypatch, tmp_path, contexts: list[dict], conn: Any):
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH", write_binding_context(tmp_path, contexts)
    )
    with (
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection",
            return_value=conn,
        ),
        mock.patch(
            "openstack_sync.hooks.framework.patch_resource_status"
        ) as patch_status,
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
                BINDING_NAME: [{"object": router_flavor_object(n)} for n in names]
            },
        }
    ]


def _deleted_context(name: str) -> list[dict]:
    """A Deleted event with the empty snapshot that follows the last CR."""
    return [
        {
            "binding": BINDING_NAME,
            "type": "Event",
            "watchEvent": "Deleted",
            "object": router_flavor_object(name),
            "snapshots": {BINDING_NAME: []},
        }
    ]


def test_main_returns_zero_when_hook_disabled(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    conn = _neutron_conn()

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("pa1410"), conn
    )

    assert code == 0
    patch_status.assert_not_called()
    conn.network.flavors.assert_not_called()


def test_main_reconciles_an_already_converged_flavor(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    conn = _neutron_conn()

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("pa1410"), conn
    )

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    assert patch_status.call_args.kwargs["message"] == (
        "Successfully reconciled router flavor"
    )
    # Already converged: no writes to Neutron.
    conn.network.create_flavor.assert_not_called()
    conn.network.create_service_profile.assert_not_called()
    conn.network.associate_flavor_with_service_profile.assert_not_called()


def test_main_reports_profile_drift_on_the_cr_status(monkeypatch, tmp_path):
    """A disabled profile keeps the flavor Synced but must show on the status."""
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    conn = _neutron_conn()
    conn.network.service_profiles.return_value[0].is_enabled = False

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("pa1410"), conn
    )

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    message = patch_status.call_args.kwargs["message"]
    assert "is_enabled" in message
    assert "profile-id" in message


def test_main_reports_failure_and_skips_prune(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_PRUNE", "true")
    conn = _neutron_conn()
    # An existing flavor whose service_type cannot be changed is a hard failure.
    conn.network.flavors.return_value[0].service_type = "WRONG_TYPE"

    with mock.patch.object(hook.prune_module, "prune_removed_flavors") as prune:
        code, patch_status = _run_main(
            monkeypatch, tmp_path, _schedule_context("pa1410"), conn
        )

    assert code == 1
    assert patch_status.call_args.kwargs["sync_status"] == "Failed"
    assert "service_type" in patch_status.call_args.kwargs["message"]
    prune.assert_not_called()


def test_main_prunes_after_a_successful_reconcile(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_PRUNE", "true")
    conn = _neutron_conn()

    with mock.patch.object(hook.prune_module, "prune_removed_flavors") as prune:
        code, _ = _run_main(monkeypatch, tmp_path, _schedule_context("pa1410"), conn)

    assert code == 0
    prune.assert_called_once()
    assert [spec["name"] for spec in prune.call_args.args[1]] == ["pa1410"]


def test_main_sweeps_an_orphaned_profile_when_the_last_cr_is_deleted(
    monkeypatch, tmp_path
):
    """Deleting the last CR still collects an unbound managed profile.

    The run reconciles nothing, so the sweep opens the connection itself.
    """
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    conn = _neutron_conn()
    bound_profile = conn.network.service_profiles.return_value[0]
    orphan = types.SimpleNamespace(
        id="orphan-profile-id",
        driver="neutron_understack.l3_router.vrf.Vrf",
        is_enabled=True,
        description="pa1410 profile",
        meta_info=markers.managed_meta_info({"vni_alloc": "auto"}),
    )
    conn.network.service_profiles.return_value = [bound_profile, orphan]

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _deleted_context("pa1410"), conn
    )

    assert code == 0
    patch_status.assert_not_called()
    # The orphan, and only the orphan: the bound profile stays.
    assert [
        call.args[0] for call in conn.network.delete_service_profile.call_args_list
    ] == [orphan]
    # PRUNE gates flavor deletion, and it is off.
    conn.network.delete_flavor.assert_not_called()


def test_main_reports_a_cr_missing_cloud_credentials_without_failing(
    monkeypatch, tmp_path, caplog
):
    """A CR without credentials is reported and skipped, and prunes nothing.

    The CRD marks cloudCredentialsRef required, so the API server should reject
    it first; this guards the case where something bypasses that. The run does
    not fail, because the object is stored that way and would be unreadable on
    every retry, and a failing hook blocks its own queue in shell-operator.
    """
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_PRUNE", "true")
    obj = router_flavor_object("pa1410")
    del obj["spec"]["cloudCredentialsRef"]
    contexts = [
        {
            "binding": BINDING_NAME,
            "type": "Schedule",
            "snapshots": {BINDING_NAME: [{"object": obj}]},
        }
    ]

    with (
        caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.framework"),
        mock.patch.object(hook.prune_module, "prune_removed_flavors") as prune,
    ):
        code, patch_status = _run_main(monkeypatch, tmp_path, contexts, _neutron_conn())

    assert code == 0
    prune.assert_not_called()
    patch_status.assert_not_called()
    assert "openstack/pa1410" in caplog.text


def test_main_uses_the_credentials_named_by_each_cr(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setattr(utils, "_connection_cache", {})
    contexts = _schedule_context("pa1410")
    contexts[0]["snapshots"][BINDING_NAME][0]["object"]["spec"][
        "cloudCredentialsRef"
    ] = {"secretName": "other-secret", "cloudName": "other-cloud"}
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH", write_binding_context(tmp_path, contexts)
    )

    with (
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection",
            return_value=_neutron_conn(),
        ) as connect,
        mock.patch("openstack_sync.hooks.framework.patch_resource_status"),
        mock.patch.object(hook, "wait_for_openstack_network"),
    ):
        assert hook.main() == 0

    connect.assert_called_once_with("other-secret", "other-cloud")
