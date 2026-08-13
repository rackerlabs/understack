"""Tests for the Neutron router flavor shell-operator hook."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest import mock

import pytest

ROUTER_ENV_NAMES = (
    "BINDING_CONTEXT_PATH",
    "NEUTRON_ROUTER_FLAVOR_ENABLED",
    "NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB",
    "NEUTRON_ROUTER_FLAVOR_CRD_API_VERSION",
    "NEUTRON_ROUTER_FLAVOR_CRD_KIND",
    "NEUTRON_ROUTER_FLAVOR_CRD_BINDING_NAME",
    "NEUTRON_ROUTER_FLAVOR_CRD_RESOURCE",
    "NEUTRON_ROUTER_FLAVOR_NAMESPACE",
    "POD_NAMESPACE",
)


def reload_router_hook(monkeypatch: pytest.MonkeyPatch, *, enabled: bool):
    for env_name in ROUTER_ENV_NAMES:
        monkeypatch.delenv(env_name, raising=False)

    monkeypatch.setenv(
        "NEUTRON_ROUTER_FLAVOR_ENABLED",
        "true" if enabled else "false",
    )
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "*/15 * * * *")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    from openstack_sync.plugins.neutron.router_flavors import create_router_flavors
    from openstack_sync.plugins.neutron.router_flavors import delete_router_flavors
    from openstack_sync.plugins.neutron.router_flavors import hook
    from openstack_sync.plugins.neutron.router_flavors import router_flavors_common
    from openstack_sync.plugins.neutron.router_flavors import update_router_flavors

    importlib.reload(router_flavors_common)
    importlib.reload(create_router_flavors)
    importlib.reload(delete_router_flavors)
    importlib.reload(update_router_flavors)
    return importlib.reload(hook)


def write_binding_context(path: Path, contexts: list[dict]) -> str:
    context_path = path / "binding-context.json"
    context_path.write_text(json.dumps(contexts), encoding="utf-8")
    return str(context_path)


def router_flavor_object(name: str, spec: dict | None = None) -> dict:
    flavor_spec = {
        "name": name,
        "service_type": "L3_ROUTER_NAT",
        "description": f"{name} description",
        "driver": "neutron_understack.l3_router.vrf.Vrf",
        "profile_description": f"{name} profile",
        "meta_info": {"vni_alloc": "auto"},
    }
    flavor_spec.update(spec or {})
    return {
        "apiVersion": "neutron.understack.rackspace.net/v1alpha1",
        "kind": "NeutronRouterFlavor",
        "metadata": {
            "name": name,
            "namespace": "openstack",
            "generation": 3,
        },
        "spec": flavor_spec,
    }


def test_disabled_hook_config_is_valid_noop(monkeypatch, capsys):
    hook = reload_router_hook(monkeypatch, enabled=False)

    assert hook.HOOK_CONFIG["onStartup"] == 10
    assert "kubernetes" not in hook.HOOK_CONFIG
    assert "schedule" not in hook.HOOK_CONFIG

    with mock.patch.object(hook.sys, "argv", ["router_flavors.py", "--config"]):
        assert hook.run() == 0

    assert json.loads(capsys.readouterr().out) == hook.HOOK_CONFIG


def test_enabled_hook_config_watches_router_flavors(monkeypatch):
    hook = reload_router_hook(monkeypatch, enabled=True)

    binding = hook.HOOK_CONFIG["kubernetes"][0]
    assert "onStartup" not in hook.HOOK_CONFIG
    assert binding["name"] == "neutron-router-flavors"
    assert binding["apiVersion"] == "neutron.understack.rackspace.net/v1alpha1"
    assert binding["kind"] == "NeutronRouterFlavor"
    assert binding["executeHookOnEvent"] == ["Added", "Modified", "Deleted"]
    assert binding["jqFilter"] == ".spec"
    assert binding["includeSnapshotsFrom"] == ["neutron-router-flavors"]
    assert binding["namespace"]["nameSelector"]["matchNames"] == ["openstack"]
    assert hook.HOOK_CONFIG["schedule"] == [
        {
            "name": "hourly sync",
            "crontab": "*/15 * * * *",
            "includeSnapshotsFrom": ["neutron-router-flavors"],
        }
    ]


def test_load_router_flavors_from_snapshot(monkeypatch, tmp_path):
    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {
                    "neutron-router-flavors": [
                        {
                            "object": router_flavor_object(
                                "dynamic-vrf",
                                {"name": "dynamic_vrf"},
                            ),
                        },
                    ],
                },
            },
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)
    hook = reload_router_hook(monkeypatch, enabled=True)
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    resources = hook.load_router_flavor_resources()

    assert len(resources) == 1
    assert resources[0].name == "dynamic-vrf"
    assert resources[0].namespace == "openstack"
    assert resources[0].generation == 3
    assert resources[0].flavor["name"] == "dynamic_vrf"
    assert resources[0].flavor["driver"] == "neutron_understack.l3_router.vrf.Vrf"


def test_run_reconciles_snapshot_resources(monkeypatch, tmp_path):
    flavor = router_flavor_object("pa1410")["spec"]
    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {
                    "neutron-router-flavors": [
                        {"object": router_flavor_object("pa1410")},
                    ],
                },
            },
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)
    hook = reload_router_hook(monkeypatch, enabled=True)
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)
    fake_conn = object()
    synced_flavors = []
    pruned_flavors = []
    statuses = []

    monkeypatch.setattr(
        hook.common,
        "connect_openstack",
        lambda os_cloud: fake_conn,
    )
    monkeypatch.setattr(
        hook.common,
        "wait_for_openstack_network",
        lambda conn: None,
    )
    monkeypatch.setattr(
        hook,
        "sync_flavor",
        lambda conn, flavor_config: synced_flavors.append((conn, flavor_config)),
    )
    monkeypatch.setattr(
        hook,
        "prune_removed_flavors",
        lambda conn, flavor_configs: pruned_flavors.append((conn, flavor_configs)),
    )
    monkeypatch.setattr(
        hook,
        "patch_resource_status",
        lambda resource, sync_status, message: statuses.append(
            (resource.name, sync_status, message),
        ),
    )

    with mock.patch.object(hook.sys, "argv", ["router_flavors.py"]):
        assert hook.run() == 0

    assert synced_flavors == [(fake_conn, flavor)]
    assert pruned_flavors == [(fake_conn, [flavor])]
    assert statuses == [
        ("pa1410", "Synced", "Successfully reconciled router flavor"),
    ]


def test_run_continues_after_single_flavor_failure(monkeypatch, tmp_path):
    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {
                    "neutron-router-flavors": [
                        {"object": router_flavor_object("bad-flavor")},
                        {"object": router_flavor_object("good-flavor")},
                    ],
                },
            },
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)
    hook = reload_router_hook(monkeypatch, enabled=True)
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)
    fake_conn = object()
    attempted_flavors = []
    pruned_flavors = []
    statuses = []

    monkeypatch.setattr(
        hook.common,
        "connect_openstack",
        lambda os_cloud: fake_conn,
    )
    monkeypatch.setattr(
        hook.common,
        "wait_for_openstack_network",
        lambda conn: None,
    )

    def sync_or_fail(conn, flavor_config):
        attempted_flavors.append(flavor_config["name"])
        if flavor_config["name"] == "bad-flavor":
            raise RuntimeError("bad flavor config")

    monkeypatch.setattr(hook, "sync_flavor", sync_or_fail)
    monkeypatch.setattr(
        hook,
        "prune_removed_flavors",
        lambda conn, flavor_configs: pruned_flavors.append((conn, flavor_configs)),
    )
    monkeypatch.setattr(
        hook,
        "patch_resource_status",
        lambda resource, sync_status, message: statuses.append(
            (resource.name, sync_status, message),
        ),
    )

    with mock.patch.object(hook.sys, "argv", ["router_flavors.py"]):
        assert hook.run() == 1

    assert attempted_flavors == ["bad-flavor", "good-flavor"]
    assert pruned_flavors == []
    assert statuses == [
        ("bad-flavor", "Failed", "bad flavor config"),
        ("good-flavor", "Synced", "Successfully reconciled router flavor"),
    ]
