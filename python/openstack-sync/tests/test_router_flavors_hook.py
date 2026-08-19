"""Integration-style tests for the Neutron router flavor hook run loop."""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest

import openstack_sync.utils as utils
from openstack_sync.hooks import router_flavors as hook
from openstack_sync.plugins.neutron.router_flavors import (
    router_flavors_common as common,
)

ROUTER_ENV_NAMES = (
    "BINDING_CONTEXT_PATH",
    "NEUTRON_ROUTER_FLAVOR_ENABLED",
    "NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB",
    "NEUTRON_ROUTER_FLAVOR_CRD_API_VERSION",
    "NEUTRON_ROUTER_FLAVOR_CRD_KIND",
    "NEUTRON_ROUTER_FLAVOR_CRD_BINDING_NAME",
    "NEUTRON_ROUTER_FLAVOR_CRD_RESOURCE",
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
    for name in ROUTER_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


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
        "cloudCredentialsRef": {
            "secretName": "infrasetup",
            "cloudName": "understack",
        },
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


# ---------------------------------------------------------------------------
# HOOK_CONFIG shape
# ---------------------------------------------------------------------------


def test_disabled_hook_config_is_valid_noop(monkeypatch, capsys):
    clear_env(monkeypatch)

    config = hook.build_hook_config()

    assert config["onStartup"] == 10
    assert "kubernetes" not in config
    assert "schedule" not in config

    with mock.patch.object(hook.sys, "argv", ["router_flavors.py", "--config"]):
        assert hook.main() == 0

    assert json.loads(capsys.readouterr().out) == config


def test_crontab_does_not_enable_disabled_hook(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "*/15 * * * *")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "false")

    config = hook.build_hook_config()

    assert config["onStartup"] == 10
    assert "kubernetes" not in config
    assert "schedule" not in config


def test_enabled_hook_config_omits_schedule_without_crontab(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")

    config = hook.build_hook_config()

    assert config["kubernetes"][0]["name"] == common.CRD_BINDING_NAME
    assert "schedule" not in config


def test_enabled_hook_config_watches_router_flavors(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "*/15 * * * *")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    config = hook.build_hook_config()

    binding = config["kubernetes"][0]
    assert "onStartup" not in config
    assert binding["name"] == common.CRD_BINDING_NAME
    assert binding["apiVersion"] == common.CRD_API_VERSION
    assert binding["kind"] == common.CRD_KIND
    assert binding["executeHookOnEvent"] == ["Added", "Modified", "Deleted"]
    assert binding["jqFilter"] == "."
    assert binding["includeSnapshotsFrom"] == [common.CRD_BINDING_NAME]
    assert binding["namespace"]["nameSelector"]["matchNames"] == ["openstack"]
    assert config["schedule"] == [
        {
            "name": "hourly sync",
            "crontab": "*/15 * * * *",
            "includeSnapshotsFrom": [common.CRD_BINDING_NAME],
        }
    ]


# ---------------------------------------------------------------------------
# load_router_flavor_resources: binding context parsing
# ---------------------------------------------------------------------------


def test_load_router_flavors_from_snapshot(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {
                    common.CRD_BINDING_NAME: [
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

    resources = hook.load_router_flavor_resources()

    assert len(resources) == 1
    assert resources[0].name == "dynamic-vrf"
    assert resources[0].namespace == "openstack"
    assert resources[0].generation == 3
    assert resources[0].flavor["name"] == "dynamic_vrf"
    assert resources[0].flavor["driver"] == "neutron_understack.l3_router.vrf.Vrf"
    # cloudCredentialsRef is popped into secret_name / cloud_name
    assert resources[0].secret_name == "infrasetup"  # noqa: S105
    assert resources[0].cloud_name == "understack"
    assert "cloudCredentialsRef" not in resources[0].flavor


# ---------------------------------------------------------------------------
# main() dispatches per-object reconciliation
# ---------------------------------------------------------------------------


def test_main_reconciles_binding_context_objects(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setattr(utils, "_connection_cache", {})

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {
                    common.CRD_BINDING_NAME: [
                        {"object": router_flavor_object("pa1410")},
                    ]
                },
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    synced = []

    with (
        mock.patch(
            "openstack_sync.utils.openstack.connection.Connection",
            return_value=mock.MagicMock(),
        ),
        mock.patch.object(utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML),
        mock.patch("openstack_sync.hooks.router_flavors.wait_for_openstack_network"),
        mock.patch("openstack_sync.hooks.router_flavors.patch_flavor_status"),
        mock.patch("openstack_sync.hooks.router_flavors.prune_removed_flavors"),
        mock.patch(
            "openstack_sync.hooks.router_flavors.sync_flavor",
            side_effect=lambda conn, flavor: synced.append(flavor["name"]),
        ),
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
    ):
        result = hook.main()

    assert result == 0
    assert synced == ["pa1410"]


def test_main_returns_error_when_reconcile_fails(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setattr(utils, "_connection_cache", {})

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {
                    common.CRD_BINDING_NAME: [
                        {"object": router_flavor_object("bad-flavor")},
                    ]
                },
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    with (
        mock.patch(
            "openstack_sync.utils.openstack.connection.Connection",
            return_value=mock.MagicMock(),
        ),
        mock.patch.object(utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML),
        mock.patch("openstack_sync.hooks.router_flavors.wait_for_openstack_network"),
        mock.patch("openstack_sync.hooks.router_flavors.patch_flavor_status"),
        mock.patch("openstack_sync.hooks.router_flavors.prune_removed_flavors"),
        mock.patch(
            "openstack_sync.hooks.router_flavors.sync_flavor",
            side_effect=RuntimeError("bad flavor config"),
        ),
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
    ):
        result = hook.main()

    assert result == 1


def test_main_prunes_after_successful_full_set_reconcile(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    conn = mock.MagicMock()

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {
                    common.CRD_BINDING_NAME: [
                        {"object": router_flavor_object("pa1410")},
                        {"object": router_flavor_object("dynamic-vrf")},
                    ]
                },
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection",
            return_value=conn,
        ),
        mock.patch("openstack_sync.hooks.router_flavors.wait_for_openstack_network"),
        mock.patch("openstack_sync.hooks.router_flavors.patch_flavor_status"),
        mock.patch("openstack_sync.hooks.router_flavors.sync_flavor") as mock_sync,
        mock.patch(
            "openstack_sync.hooks.router_flavors.prune_removed_flavors"
        ) as mock_prune,
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
    ):
        result = hook.main()

    assert result == 0
    assert [call.args[1]["name"] for call in mock_sync.call_args_list] == [
        "dynamic-vrf",
        "pa1410",
    ]
    mock_prune.assert_called_once()
    assert mock_prune.call_args.args[0] is conn
    assert [flavor["name"] for flavor in mock_prune.call_args.args[1]] == [
        "dynamic-vrf",
        "pa1410",
    ]


def test_main_continues_after_failure_and_skips_prune(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    conn = mock.MagicMock()

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {
                    common.CRD_BINDING_NAME: [
                        {"object": router_flavor_object("bad-flavor")},
                        {"object": router_flavor_object("good-flavor")},
                    ]
                },
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)
    seen = []

    def sync_flavor(conn, flavor):
        seen.append(flavor["name"])
        if flavor["name"] == "bad-flavor":
            raise RuntimeError("bad flavor config")

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection",
            return_value=conn,
        ),
        mock.patch("openstack_sync.hooks.router_flavors.wait_for_openstack_network"),
        mock.patch(
            "openstack_sync.hooks.router_flavors.patch_flavor_status"
        ) as mock_status,
        mock.patch(
            "openstack_sync.hooks.router_flavors.sync_flavor",
            side_effect=sync_flavor,
        ),
        mock.patch(
            "openstack_sync.hooks.router_flavors.prune_removed_flavors"
        ) as mock_prune,
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
    ):
        result = hook.main()

    assert result == 1
    assert seen == ["bad-flavor", "good-flavor"]
    assert [call.args[1] for call in mock_status.call_args_list] == [
        "Failed",
        "Synced",
    ]
    mock_prune.assert_not_called()
