"""Integration-style tests for the Neutron router flavor hook run loop."""

from __future__ import annotations

import importlib
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
    "NEUTRON_ROUTER_FLAVOR_CRD_BINDING_NAME",
    "NEUTRON_ROUTER_FLAVOR_PRUNE",
    "NEUTRON_ROUTER_FLAVOR_STATUS_ENABLED",
    "NEUTRON_ROUTER_FLAVOR_READY_RETRIES",
    "NEUTRON_ROUTER_FLAVOR_READY_DELAY",
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
# hook config shape
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


def test_common_import_is_safe_with_bad_runtime_env(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "maybe")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_STATUS_ENABLED", "maybe")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_READY_RETRIES", "soon")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_READY_DELAY", "later")

    importlib.reload(common)


def test_disabled_hook_config_does_not_parse_runtime_env(monkeypatch):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "maybe")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_STATUS_ENABLED", "maybe")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_READY_RETRIES", "soon")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_READY_DELAY", "later")

    config = hook.build_hook_config()

    assert config["onStartup"] == 10
    assert "kubernetes" not in config


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
    assert binding["apiVersion"] == common.crd_api_version()
    assert binding["kind"] == common.crd_kind()
    assert binding["executeHookOnEvent"] == ["Added", "Modified", "Deleted"]
    assert binding["jqFilter"] == "."
    assert binding["includeSnapshotsFrom"] == [common.CRD_BINDING_NAME]
    assert binding["namespace"]["nameSelector"]["matchNames"] == ["openstack"]
    assert binding["queue"] == common.CRD_BINDING_NAME
    assert config["schedule"] == [
        {
            "name": "hourly sync",
            "crontab": "*/15 * * * *",
            "includeSnapshotsFrom": [common.CRD_BINDING_NAME],
            "queue": common.CRD_BINDING_NAME,
        }
    ]


# ---------------------------------------------------------------------------
# load_router_flavor_hook_inputs: binding context parsing
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

    hook_inputs = hook.load_router_flavor_hook_inputs()
    resources = hook_inputs.resources_to_reconcile

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
    # Schedule contexts fall through to snapshot parsing, so desired equals
    # resources_to_reconcile.
    assert hook_inputs.desired_resources_for_prune == resources
    assert hook_inputs.deleted_resources == []


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
            side_effect=lambda conn, flavor, profiles: synced.append(flavor["name"]),
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


def test_main_prunes_deleted_only_credentials(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "true")
    conn = mock.MagicMock()

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Deleted",
                "object": router_flavor_object("pa1410"),
                "snapshots": {common.CRD_BINDING_NAME: []},
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection",
            return_value=conn,
        ) as mock_connect,
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
    mock_connect.assert_called_once_with("infrasetup", "understack")
    mock_sync.assert_not_called()
    mock_prune.assert_called_once_with(conn, [], authoritative_empty_desired=True)


def test_main_returns_error_when_deleted_only_connection_fails(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "true")

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Deleted",
                "object": router_flavor_object("pa1410"),
                "snapshots": {common.CRD_BINDING_NAME: []},
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection",
            side_effect=RuntimeError("secret missing"),
        ) as mock_connect,
        mock.patch(
            "openstack_sync.hooks.router_flavors.wait_for_openstack_network"
        ) as mock_wait,
        mock.patch("openstack_sync.hooks.router_flavors.patch_flavor_status"),
        mock.patch("openstack_sync.hooks.router_flavors.sync_flavor") as mock_sync,
        mock.patch(
            "openstack_sync.hooks.router_flavors.prune_removed_flavors"
        ) as mock_prune,
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
    ):
        result = hook.main()

    assert result == 1
    mock_connect.assert_called_once_with("infrasetup", "understack")
    mock_wait.assert_not_called()
    mock_sync.assert_not_called()
    mock_prune.assert_not_called()


def test_main_returns_error_when_deleted_only_prune_fails(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "true")
    conn = mock.MagicMock()

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Deleted",
                "object": router_flavor_object("pa1410"),
                "snapshots": {common.CRD_BINDING_NAME: []},
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection",
            return_value=conn,
        ) as mock_connect,
        mock.patch(
            "openstack_sync.hooks.router_flavors.wait_for_openstack_network"
        ) as mock_wait,
        mock.patch("openstack_sync.hooks.router_flavors.patch_flavor_status"),
        mock.patch("openstack_sync.hooks.router_flavors.sync_flavor") as mock_sync,
        mock.patch(
            "openstack_sync.hooks.router_flavors.prune_removed_flavors",
            side_effect=RuntimeError("delete failed"),
        ) as mock_prune,
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
    ):
        result = hook.main()

    assert result == 1
    mock_connect.assert_called_once_with("infrasetup", "understack")
    mock_wait.assert_called_once_with(conn)
    mock_sync.assert_not_called()
    mock_prune.assert_called_once_with(conn, [], authoritative_empty_desired=True)


def test_main_ignores_deleted_only_credentials_when_prune_is_disabled(
    monkeypatch, tmp_path
):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "false")

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Deleted",
                "object": router_flavor_object("pa1410"),
                "snapshots": {common.CRD_BINDING_NAME: []},
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection"
        ) as mock_connect,
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
    mock_connect.assert_not_called()
    mock_sync.assert_not_called()
    mock_prune.assert_not_called()


def test_main_prunes_active_and_deleted_only_credentials(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "true")
    active_conn = mock.MagicMock(name="active_conn")
    deleted_conn = mock.MagicMock(name="deleted_conn")

    active_object = router_flavor_object("pa1410")
    deleted_object = router_flavor_object(
        "other-cloud-flavor",
        {
            "cloudCredentialsRef": {
                "secretName": "other-secret",
                "cloudName": "other-cloud",
            }
        },
    )
    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Deleted",
                "object": deleted_object,
                "snapshots": {
                    common.CRD_BINDING_NAME: [{"object": active_object}],
                },
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    def connect(secret_name, cloud_name):
        if (secret_name, cloud_name) == ("infrasetup", "understack"):
            return active_conn
        if (secret_name, cloud_name) == ("other-secret", "other-cloud"):
            return deleted_conn
        raise AssertionError((secret_name, cloud_name))

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection",
            side_effect=connect,
        ),
        mock.patch("openstack_sync.hooks.router_flavors.wait_for_openstack_network"),
        mock.patch("openstack_sync.hooks.router_flavors.patch_flavor_status"),
        mock.patch("openstack_sync.hooks.router_flavors.sync_flavor"),
        mock.patch(
            "openstack_sync.hooks.router_flavors.prune_removed_flavors"
        ) as mock_prune,
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
    ):
        result = hook.main()

    assert result == 0
    assert mock_prune.call_args_list == [
        mock.call(active_conn, [mock.ANY]),
        mock.call(deleted_conn, [], authoritative_empty_desired=True),
    ]
    assert mock_prune.call_args_list[0].args[1][0]["name"] == "pa1410"


def test_main_skips_empty_snapshot_prune_without_credentials(monkeypatch, tmp_path):
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "true")

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": "hourly sync",
                "type": "Schedule",
                "snapshots": {common.CRD_BINDING_NAME: []},
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection"
        ) as mock_connect,
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
    mock_connect.assert_not_called()
    mock_sync.assert_not_called()
    mock_prune.assert_not_called()


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

    def sync_flavor(conn, flavor, profiles):
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


# ---------------------------------------------------------------------------
# Event-driven scenarios: reconcile only the changed CR while prune uses
# the full snapshot delivered by shell-operator.
# ---------------------------------------------------------------------------


def router_flavor_object_with_status(
    name: str,
    *,
    generation: int = 3,
    status: dict | None = None,
    spec: dict | None = None,
) -> dict:
    """Build a NeutronRouterFlavor object with optional status/generation.

    Mirrors :func:`router_flavor_object` but allows tests to control the
    metadata.generation and status subresource used by the Modified-event
    status-current guard.
    """
    obj = router_flavor_object(name, spec)
    obj["metadata"]["generation"] = generation
    if status is not None:
        obj["status"] = status
    return obj


def test_added_event_reconciles_only_added_resource(monkeypatch, tmp_path):
    """An Added event reconciles only the new CR; prune sees the full snapshot.

    Regression guard for the noise-on-create scenario: creating a new CR must
    not reconcile the four unrelated CRs already present in Neutron.
    """
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    conn = mock.MagicMock()

    added = router_flavor_object("crud_svi")
    other_names = ["dynamic_vrf", "pa1410", "static_vrf", "svi"]
    snapshot_objects = [router_flavor_object(name) for name in other_names] + [added]

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Added",
                "object": added,
                "snapshots": {
                    common.CRD_BINDING_NAME: [
                        {"object": obj} for obj in snapshot_objects
                    ],
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
    assert [call.args[1]["name"] for call in mock_sync.call_args_list] == ["crud_svi"]
    mock_prune.assert_called_once()
    prune_flavors = mock_prune.call_args.args[1]
    assert sorted(flavor["name"] for flavor in prune_flavors) == sorted(
        other_names + ["crud_svi"]
    )
    assert "authoritative_empty_desired" not in mock_prune.call_args.kwargs


def test_deleted_event_reconciles_none_and_prunes_with_remaining_snapshot(
    monkeypatch, tmp_path
):
    """Delete of one CR while others remain in the same credential group.

    Regression guard for the exact log scenario: deleting crud_svi while
    four remain must not reconcile any of the remaining flavors. Prune
    receives the snapshot of the remaining four and does NOT set
    authoritative_empty_desired, so it only removes the flavor that is
    absent from the snapshot.
    """
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_PRUNE", "true")
    conn = mock.MagicMock()

    deleted = router_flavor_object("crud_svi")
    remaining_names = ["dynamic_vrf", "pa1410", "static_vrf", "svi"]
    remaining = [router_flavor_object(name) for name in remaining_names]

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Deleted",
                "object": deleted,
                "snapshots": {
                    common.CRD_BINDING_NAME: [{"object": obj} for obj in remaining],
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
    mock_sync.assert_not_called()
    mock_prune.assert_called_once()
    prune_flavors = mock_prune.call_args.args[1]
    assert sorted(flavor["name"] for flavor in prune_flavors) == sorted(remaining_names)
    # authoritative_empty_desired must NOT be set: snapshot still has items.
    assert mock_prune.call_args.kwargs.get("authoritative_empty_desired") is not True


def test_modified_event_skipped_when_status_already_current(monkeypatch, tmp_path):
    """Status-only Modified events must not trigger OpenStack work.

    The hook's own status patch surfaces as a Modified event with the same
    metadata.generation. If status already reflects that generation as Synced,
    the hook must skip both reconcile and prune to break the feedback loop.
    """
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    obj = router_flavor_object_with_status(
        "crud_svi",
        generation=7,
        status={
            "syncStatus": "Synced",
            "observedGeneration": 7,
            "message": "Successfully reconciled router flavor",
        },
    )

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Modified",
                "object": obj,
                "snapshots": {common.CRD_BINDING_NAME: [{"object": obj}]},
            }
        ],
    )
    monkeypatch.setenv("BINDING_CONTEXT_PATH", context_path)

    with (
        mock.patch(
            "openstack_sync.hooks.router_flavors.get_openstack_connection"
        ) as mock_connect,
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
    mock_connect.assert_not_called()
    mock_sync.assert_not_called()
    mock_prune.assert_not_called()


def test_modified_event_reconciles_when_generation_bumped(monkeypatch, tmp_path):
    """A real spec change bumps metadata.generation past observedGeneration.

    The status-current guard must not skip these events: the spec is drifted
    from what the operator last reconciled, so reconcile must run.
    """
    clear_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    conn = mock.MagicMock()

    obj = router_flavor_object_with_status(
        "crud_svi",
        generation=8,
        status={
            "syncStatus": "Synced",
            "observedGeneration": 7,
            "message": "Successfully reconciled router flavor",
        },
    )

    context_path = write_binding_context(
        tmp_path,
        [
            {
                "binding": common.CRD_BINDING_NAME,
                "type": "Event",
                "watchEvent": "Modified",
                "object": obj,
                "snapshots": {common.CRD_BINDING_NAME: [{"object": obj}]},
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
        mock.patch("openstack_sync.hooks.router_flavors.prune_removed_flavors"),
        mock.patch.object(hook.sys, "argv", ["router_flavors.py"]),
    ):
        result = hook.main()

    assert result == 0
    assert [call.args[1]["name"] for call in mock_sync.call_args_list] == ["crud_svi"]
