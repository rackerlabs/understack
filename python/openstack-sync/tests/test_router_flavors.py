"""Tests for the Neutron router flavors hook."""

from __future__ import annotations

import json
import logging
from unittest import mock

import pytest

import openstack_sync.utils as utils
from openstack_sync.hooks import router_flavors

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


def _fake_conn():
    return mock.MagicMock(name="fake_conn")


def _router_flavor_object(
    name: str,
    spec: dict | None = None,
    status: dict | None = None,
) -> dict:
    flavor_spec = {
        "name": name,
        "driver": "some.Driver",
        "cloudCredentialsRef": {
            "secretName": "infrasetup",
            "cloudName": "understack",
        },
    }
    flavor_spec.update(spec or {})
    obj = {
        "metadata": {
            "name": name,
            "namespace": "openstack",
            "generation": 1,
        },
        "spec": flavor_spec,
    }
    if status is not None:
        obj["status"] = status
    return obj


def _snapshot_context(*objects: dict) -> list[dict]:
    return [
        {
            "binding": "hourly sync",
            "type": "Schedule",
            "snapshots": {
                router_flavors.CRD_BINDING_NAME: [{"object": obj} for obj in objects],
            },
        }
    ]


# ---------------------------------------------------------------------------
# build_hook_config: reads env at call time so monkeypatch works directly
# ---------------------------------------------------------------------------


def test_router_flavor_hook_config_disabled(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "false")

    config = router_flavors.build_hook_config()

    assert config["onStartup"] == 10
    assert "kubernetes" not in config
    assert "schedule" not in config


def test_router_flavor_hook_config_omits_schedule_without_crontab(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.delenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", raising=False)
    monkeypatch.delenv("POD_NAMESPACE", raising=False)

    config = router_flavors.build_hook_config()

    assert config["kubernetes"][0]["name"] == router_flavors.CRD_BINDING_NAME
    assert "schedule" not in config


def test_router_flavor_hook_config_omits_schedule_with_empty_crontab(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "")
    monkeypatch.delenv("POD_NAMESPACE", raising=False)

    config = router_flavors.build_hook_config()

    assert config["kubernetes"][0]["name"] == router_flavors.CRD_BINDING_NAME
    assert "schedule" not in config


def test_router_flavor_hook_config_uses_pod_namespace(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    config = router_flavors.build_hook_config()

    assert config["kubernetes"][0]["namespace"] == {
        "nameSelector": {"matchNames": ["openstack"]}
    }
    assert config["kubernetes"][0]["queue"] == router_flavors.CRD_BINDING_NAME
    assert config["schedule"][0]["crontab"] == "0 * * * *"
    assert config["schedule"][0]["queue"] == router_flavors.CRD_BINDING_NAME
    assert "onStartup" not in config


def test_router_flavor_hook_config_custom_crontab(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "*/15 * * * *")
    monkeypatch.delenv("POD_NAMESPACE", raising=False)

    config = router_flavors.build_hook_config()

    assert config["schedule"][0]["crontab"] == "*/15 * * * *"


def test_router_flavor_hook_config_uses_full_object_filter(monkeypatch):
    """JqFilter must be '.' so cloudCredentialsRef is available at reconcile time."""
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.delenv("POD_NAMESPACE", raising=False)

    config = router_flavors.build_hook_config()

    assert config["kubernetes"][0]["jqFilter"] == "."


def test_router_flavor_hook_config_printed_on_config_flag(monkeypatch, capsys):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "*/15 * * * *")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    with mock.patch.object(
        router_flavors.sys, "argv", ["router_flavors.py", "--config"]
    ):
        assert router_flavors.main() == 0

    config = json.loads(capsys.readouterr().out)
    assert config["kubernetes"][0]["namespace"]["nameSelector"]["matchNames"] == [
        "openstack"
    ]
    assert config["schedule"][0]["crontab"] == "*/15 * * * *"


# ---------------------------------------------------------------------------
# binding context parsing
# ---------------------------------------------------------------------------


def test_load_router_flavor_resources_keeps_current_status():
    status = {
        "syncStatus": "Synced",
        "message": "Successfully reconciled router flavor",
        "observedGeneration": 1,
    }
    contexts = _snapshot_context(_router_flavor_object("flavor-a", status=status))

    resources = router_flavors.load_router_flavor_resources(contexts)

    assert resources[0].current_status == status


def test_patch_flavor_status_passes_current_status():
    status = {"syncStatus": "Synced", "message": "ok", "observedGeneration": 1}
    secret_name = "infrasetup"  # noqa: S105
    resource = router_flavors.RouterFlavorResource(
        flavor={"name": "flavor-a", "driver": "some.Driver"},
        name="flavor-a",
        namespace="openstack",
        generation=1,
        secret_name=secret_name,
        cloud_name="understack",
        current_status=status,
    )

    with mock.patch(
        "openstack_sync.hooks.router_flavors.patch_resource_status"
    ) as mock_patch:
        router_flavors.patch_flavor_status(resource, "Synced", "ok")

    assert mock_patch.call_args.kwargs["current_status"] == status


# ---------------------------------------------------------------------------
# reconcile_router_flavor_resources: credential resolution and sync delegation
# ---------------------------------------------------------------------------


def test_reconcile_uses_cloudcredentialsref():
    """Per-resource cloudCredentialsRef is used to connect to OpenStack."""
    resource = router_flavors.load_router_flavor_resources(
        _snapshot_context(
            _router_flavor_object(
                "test-flavor",
                {
                    "cloudCredentialsRef": {
                        "secretName": "baremetal-manage",
                        "cloudName": "understack",
                    },
                },
            )
        )
    )[0]
    conn = _fake_conn()

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
    ):
        result = router_flavors.reconcile_router_flavor_resources([resource])

    assert result == 0
    mock_connect.assert_called_once_with("baremetal-manage", "understack")
    mock_sync.assert_called_once_with(conn, resource.flavor)
    mock_prune.assert_called_once_with(conn, [resource.flavor])


def test_reconcile_requires_cloudcredentialsref():
    obj = {
        "metadata": {"name": "no-ref-flavor"},
        "spec": {"name": "no-ref-flavor", "driver": "some.Driver"},
    }

    with pytest.raises(
        router_flavors.ConfigError,
        match="cloudCredentialsRef is required",
    ):
        router_flavors.load_router_flavor_resources(_snapshot_context(obj))


def test_reconcile_requires_complete_cloudcredentialsref():
    obj = {
        "metadata": {"name": "partial-flavor"},
        "spec": {
            "name": "partial-flavor",
            "driver": "some.Driver",
            "cloudCredentialsRef": {"secretName": "custom-secret"},
        },
    }

    with pytest.raises(
        router_flavors.ConfigError,
        match=r"cloudCredentialsRef\.cloudName",
    ):
        router_flavors.load_router_flavor_resources(_snapshot_context(obj))


# ---------------------------------------------------------------------------
# main(): binding context dispatch
# ---------------------------------------------------------------------------


def test_main_dispatches_to_reconcile(monkeypatch, tmp_path):
    """main() reads BINDING_CONTEXT_PATH and dispatches each object."""
    monkeypatch.setattr(utils, "_connection_cache", {})
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    binding_context = json.dumps(_snapshot_context(_router_flavor_object("flavor-a")))

    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text(binding_context)
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with (
        mock.patch(
            "openstack_sync.utils.openstack.connection.Connection",
            return_value=_fake_conn(),
        ),
        mock.patch.object(utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML),
        mock.patch("openstack_sync.hooks.router_flavors.wait_for_openstack_network"),
        mock.patch("openstack_sync.hooks.router_flavors.patch_flavor_status"),
        mock.patch("openstack_sync.hooks.router_flavors.prune_removed_flavors"),
        mock.patch("openstack_sync.hooks.router_flavors.sync_flavor") as mock_sync,
        mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]),
    ):
        result = router_flavors.main()

    assert result == 0
    mock_sync.assert_called_once()


def test_main_returns_error_on_invalid_json(monkeypatch, caplog, tmp_path):
    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text("not-json")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with (
        caplog.at_level(logging.ERROR, logger="openstack_sync.hooks.router_flavors"),
        mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]),
    ):
        result = router_flavors.main()

    assert result == 1
    assert "failed to parse binding context" in caplog.text


def test_main_returns_zero_on_empty_context(monkeypatch, tmp_path):
    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text("")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]):
        result = router_flavors.main()

    assert result == 0


def test_main_returns_zero_when_no_context_path(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.delenv("BINDING_CONTEXT_PATH", raising=False)

    with mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]):
        result = router_flavors.main()

    assert result == 0
