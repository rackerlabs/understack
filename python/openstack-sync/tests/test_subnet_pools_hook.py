"""Tests for the subnet pool hook: how the plugin wires into the framework.

The generic driver is covered in ``test_framework.py``; these tests cover only
what is specific to this plugin, plus one end-to-end run through ``main()``.
Nautobot resolution is covered in ``test_subnet_pools_nautobot.py`` and Neutron
convergence in ``test_subnet_pools_reconcile.py``.
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
from openstack_sync.hooks import subnet_pools as hook
from openstack_sync.hooks.framework import CleanupPolicy
from openstack_sync.hooks.framework import HookConfig
from openstack_sync.hooks.framework import PruneRequest
from openstack_sync.plugins.neutron.subnet_pools.config import BINDING_NAME
from openstack_sync.plugins.neutron.subnet_pools.config import ENV_PREFIX
from openstack_sync.plugins.neutron.subnet_pools.config import OWNERSHIP_TAG

CRD_API_VERSION = "neutron.understack.rackspace.net/v1alpha1"
CRD_KIND = "NeutronSubnetPool"
CRD_RESOURCE = "neutronsubnetpools.neutron.understack.rackspace.net"

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


def _spec() -> dict[str, Any]:
    """A CR carrying the full pool contract; Nautobot supplies only the CIDRs."""
    return {
        "address_scope": {"name": "publicnet-ip4"},
        "minimum_prefix_length": 27,
        "default_prefix_length": 28,
        "maximum_prefix_length": 30,
        "nautobot": {
            "url": "https://nautobot.example.test",
            "api_version": "2.0",
            "tokenSecretRef": {"secretName": "nautobot-token", "key": "token"},
            "prefix_refs": [
                {"id": "2bc3ecab-b6dc-46cd-9bd4-1c0ea8a07f87"},
                {"id": "53c8ee3b-09b9-41ab-a413-b1a1f5ecec6a"},
            ],
            "require": {
                "location": "iad3-dev",
                "tags": ["openstack-subnet-pool"],
                "status": "Active",
                "type": "pool",
                "namespace": "Rackspace",
            },
        },
        "is_default": False,
        "shared": True,
        "tags": ["managed-by-openstack-sync"],
    }


def subnet_pool_object(name: str, spec: dict | None = None) -> dict:
    pool_spec = _spec()
    pool_spec["name"] = name
    pool_spec["cloudCredentialsRef"] = {
        "secretName": "infrasetup",
        "cloudName": "understack",
    }
    pool_spec.update(spec or {})
    return {
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "metadata": {"name": name, "namespace": "openstack", "generation": 3},
        "spec": pool_spec,
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


def test_enabled_config_flag_watches_this_crd(monkeypatch, capsys):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setattr(hook.sys, "argv", ["subnet_pools.py", "--config"])

    assert hook.main() == 0
    config = json.loads(capsys.readouterr().out)
    (binding,) = config["kubernetes"]
    assert binding["name"] == BINDING_NAME
    assert binding["kind"] == CRD_KIND


# ---------------------------------------------------------------------------
# Plugin wiring
# ---------------------------------------------------------------------------


def test_plugin_reconcile_delegates_to_sync_subnet_pool():
    plugin = hook.SubnetPoolPlugin(_config(namespace="openstack"))
    conn = mock.MagicMock()
    cache: dict[str, Any] = {}
    spec = {"name": "pool-a"}

    with mock.patch.object(
        hook.reconcile_module, "sync_subnet_pool", return_value=[]
    ) as sync_subnet_pool:
        notes = plugin.reconcile(conn, spec, cache)

    assert notes == []
    sync_subnet_pool.assert_called_once_with(conn, spec, "openstack", cache)


def test_plugin_reconcile_falls_back_to_pod_namespace_when_unset():
    plugin = hook.SubnetPoolPlugin(_config(namespace=None))
    conn = mock.MagicMock()

    with (
        mock.patch.object(
            hook.reconcile_module, "sync_subnet_pool", return_value=[]
        ) as sync_subnet_pool,
        mock.patch.object(hook, "pod_namespace", return_value="fallback-ns"),
    ):
        plugin.reconcile(conn, {"name": "pool-a"}, {})

    assert sync_subnet_pool.call_args.args[2] == "fallback-ns"


def test_plugin_wait_for_api_uses_configured_retry_budget():
    plugin = hook.SubnetPoolPlugin(_config(ready_retries=5, ready_delay=0.25))
    conn = mock.MagicMock()

    with mock.patch.object(hook, "wait_for_openstack_network") as wait:
        plugin.wait_for_api(conn)

    wait.assert_called_once_with(conn, retries=5, delay=0.25)


def test_plugin_prune_resolves_desired_names_before_deleting():
    plugin = hook.SubnetPoolPlugin(_config(prune=False, namespace="openstack"))
    conn = mock.MagicMock()
    specs = [{"nautobot": {"prefix_refs": [{"id": "x"}]}}]

    with (
        mock.patch.object(
            hook.reconcile_module, "resolve_desired_names", return_value=["a"]
        ) as resolve,
        mock.patch.object(hook.prune_module, "prune_removed_subnet_pools") as prune,
    ):
        plugin.prune_resources(
            conn,
            PruneRequest(
                credentials=("infrasetup", "understack"),
                desired_specs=specs,
                authoritative_empty=False,
            ),
        )

    # The pool name is on the CR, so prune is fed names read from the specs.
    resolve.assert_called_once_with(specs)
    prune.assert_called_once_with(conn, ["a"], authoritative_empty=False)


def test_plugin_prune_forwards_authoritative_empty_when_enabled():
    plugin = hook.SubnetPoolPlugin(_config(prune=True, namespace="openstack"))
    conn = mock.MagicMock()
    specs = [{"nautobot": {"prefix_refs": [{"id": "x"}]}}]

    with (
        mock.patch.object(
            hook.reconcile_module, "resolve_desired_names", return_value=["a"]
        ),
        mock.patch.object(hook.prune_module, "prune_removed_subnet_pools") as prune,
    ):
        plugin.prune_resources(
            conn,
            PruneRequest(
                credentials=("infrasetup", "understack"),
                desired_specs=specs,
                authoritative_empty=True,
            ),
        )

    prune.assert_called_once_with(conn, ["a"], authoritative_empty=True)


def test_plugin_cleanup_policy_has_no_prune_step_when_disabled():
    plugin = hook.SubnetPoolPlugin(_config(prune=False))

    assert plugin.cleanup_policy() is CleanupPolicy.NONE
    assert plugin.should_run_prune() is False
    assert plugin.uses_finalizer() is False


def test_plugin_uses_finalized_prune_when_enabled():
    plugin = hook.SubnetPoolPlugin(_config(prune=True))

    assert plugin.cleanup_policy() is CleanupPolicy.FINALIZED_PRUNE
    assert plugin.should_run_prune() is True
    assert plugin.uses_finalizer() is True


# ---------------------------------------------------------------------------
# End to end through main()
# ---------------------------------------------------------------------------


def _prefix(prefix: str, prefix_id: str) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        id=prefix_id,
        prefix=prefix,
        status=types.SimpleNamespace(name="Active"),
        type="pool",
        namespace=types.SimpleNamespace(name="Rackspace"),
        locations=[types.SimpleNamespace(name="iad3-dev")],
        tags=[types.SimpleNamespace(name="openstack-subnet-pool")],
    )


def _neutron_conn() -> Any:
    """A Neutron connection that already holds the desired subnet pool."""
    scope = types.SimpleNamespace(id="scope-id", name="publicnet-ip4", ip_version=4)
    pool = types.SimpleNamespace(
        id="pool-id",
        name="PUBLIC-IP-POOL",
        address_scope_id="scope-id",
        project_id=None,
        prefixes=["204.232.163.128/25", "10.4.88.0/24"],
        ip_version=4,
        default_prefix_length=28,
        minimum_prefix_length=27,
        maximum_prefix_length=30,
        description="",
        is_default=False,
        is_shared=True,
        tags=["managed-by-openstack-sync", OWNERSHIP_TAG],
    )
    conn = mock.MagicMock()
    conn.network.address_scopes.return_value = [scope]
    conn.network.subnet_pools.return_value = [pool]
    return conn


def _nautobot_client() -> Any:
    # Keyed by id so reconcile can resolve each referenced prefix's CIDR.
    prefixes = {
        "2bc3ecab-b6dc-46cd-9bd4-1c0ea8a07f87": _prefix(
            "204.232.163.128/25", "2bc3ecab-b6dc-46cd-9bd4-1c0ea8a07f87"
        ),
        "53c8ee3b-09b9-41ab-a413-b1a1f5ecec6a": _prefix(
            "10.4.88.0/24", "53c8ee3b-09b9-41ab-a413-b1a1f5ecec6a"
        ),
    }
    client = mock.MagicMock()
    # reconcile passes id plus (when require.location is set) location=; accept
    # and ignore the extra kwargs so the fake resolves purely by id.
    client.ipam.prefixes.get.side_effect = lambda id, **_: prefixes.get(id)
    return client


def _schedule_context(*names: str) -> list[dict]:
    return [
        {
            "binding": BINDING_NAME,
            "type": "Schedule",
            "snapshots": {
                BINDING_NAME: [{"object": subnet_pool_object(n)} for n in names]
            },
        }
    ]


def _run_main(monkeypatch, tmp_path, contexts: list[dict], conn: Any):
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH", write_binding_context(tmp_path, contexts)
    )
    with (
        mock.patch.object(hook.sys, "argv", ["subnet_pools.py"]),
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
        mock.patch(
            "openstack_sync.plugins.neutron.subnet_pools.nautobot.read_secret_key",
            return_value="nb-token",
        ),
        mock.patch(
            "openstack_sync.plugins.neutron.subnet_pools.nautobot.pynautobot.api",
            return_value=_nautobot_client(),
        ),
    ):
        code = hook.main()
    return code, patch_status


def test_main_returns_zero_when_hook_disabled(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    conn = _neutron_conn()

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("PUBLIC-IP-POOL"), conn
    )

    assert code == 0
    patch_status.assert_not_called()
    conn.network.subnet_pools.assert_not_called()


def test_main_reconciles_an_already_converged_pool(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    conn = _neutron_conn()

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("PUBLIC-IP-POOL"), conn
    )

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    # Already converged: no writes to Neutron.
    conn.network.create_subnet_pool.assert_not_called()
    conn.network.update_subnet_pool.assert_not_called()
    conn.network.set_tags.assert_not_called()


def test_main_creates_a_missing_pool(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    conn = _neutron_conn()
    conn.network.subnet_pools.return_value = []
    created = types.SimpleNamespace(
        id="pool-id",
        name="PUBLIC-IP-POOL",
        prefixes=["204.232.163.128/25", "10.4.88.0/24"],
        ip_version=4,
        tags=[],
    )
    conn.network.create_subnet_pool.return_value = created

    code, patch_status = _run_main(
        monkeypatch, tmp_path, _schedule_context("PUBLIC-IP-POOL"), conn
    )

    assert code == 0
    assert patch_status.call_args.kwargs["sync_status"] == "Synced"
    create_kwargs = conn.network.create_subnet_pool.call_args.kwargs
    assert create_kwargs["name"] == "PUBLIC-IP-POOL"
    assert create_kwargs["address_scope_id"] == "scope-id"
    assert create_kwargs["prefixes"] == ["204.232.163.128/25", "10.4.88.0/24"]
    conn.network.set_tags.assert_called_once_with(
        created, ["managed-by-openstack-sync", OWNERSHIP_TAG]
    )


def test_main_reports_failure_and_skips_prune(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_PRUNE", "true")
    conn = _neutron_conn()
    # An existing pool with a different IP version is a hard failure.
    conn.network.subnet_pools.return_value[0].ip_version = 6

    with mock.patch.object(hook.prune_module, "prune_removed_subnet_pools") as prune:
        code, patch_status = _run_main(
            monkeypatch, tmp_path, _schedule_context("PUBLIC-IP-POOL"), conn
        )

    assert code == 1
    assert patch_status.call_args.kwargs["sync_status"] == "Failed"
    prune.assert_not_called()


def test_main_prunes_after_a_successful_reconcile(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setenv(f"{ENV_PREFIX}_PRUNE", "true")
    conn = _neutron_conn()

    with mock.patch.object(hook.prune_module, "prune_removed_subnet_pools") as prune:
        code, _ = _run_main(
            monkeypatch, tmp_path, _schedule_context("PUBLIC-IP-POOL"), conn
        )

    assert code == 0
    prune.assert_called_once()
    # Prune receives resolved Neutron pool names, not raw CR specs.
    assert prune.call_args.args[1] == ["PUBLIC-IP-POOL"]


def test_main_uses_the_credentials_named_by_each_cr(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    set_crd_identity(monkeypatch)
    monkeypatch.setenv(f"{ENV_PREFIX}_ENABLED", "true")
    monkeypatch.setattr(utils, "_connection_cache", {})
    contexts = _schedule_context("PUBLIC-IP-POOL")
    contexts[0]["snapshots"][BINDING_NAME][0]["object"]["spec"][
        "cloudCredentialsRef"
    ] = {"secretName": "other-secret", "cloudName": "other-cloud"}
    monkeypatch.setenv(
        "BINDING_CONTEXT_PATH", write_binding_context(tmp_path, contexts)
    )

    with (
        mock.patch.object(hook.sys, "argv", ["subnet_pools.py"]),
        mock.patch(
            "openstack_sync.hooks.framework.get_openstack_connection",
            return_value=_neutron_conn(),
        ) as connect,
        mock.patch("openstack_sync.hooks.framework.patch_resource_status"),
        mock.patch.object(hook, "wait_for_openstack_network"),
        mock.patch(
            "openstack_sync.plugins.neutron.subnet_pools.nautobot.read_secret_key",
            return_value="nb-token",
        ),
        mock.patch(
            "openstack_sync.plugins.neutron.subnet_pools.nautobot.pynautobot.api",
            return_value=_nautobot_client(),
        ),
    ):
        assert hook.main() == 0

    connect.assert_called_once_with("other-secret", "other-cloud")
