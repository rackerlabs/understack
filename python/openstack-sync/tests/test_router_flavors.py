"""Tests for the Neutron router flavors hook."""

from __future__ import annotations

import json
from unittest import mock

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


# ---------------------------------------------------------------------------
# build_hook_config — reads env at call time so monkeypatch works directly
# ---------------------------------------------------------------------------


def test_router_flavor_hook_config_disabled(monkeypatch):
    monkeypatch.delenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", raising=False)

    config = router_flavors.build_hook_config()

    assert config["onStartup"] == 10
    assert "kubernetes" not in config
    assert "schedule" not in config


def test_router_flavor_hook_config_uses_pod_namespace(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    config = router_flavors.build_hook_config()

    assert config["kubernetes"][0]["namespace"] == {
        "nameSelector": {"matchNames": ["openstack"]}
    }
    assert config["schedule"][0]["crontab"] == "0 * * * *"
    assert "onStartup" not in config


def test_router_flavor_hook_config_custom_crontab(monkeypatch):
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "*/15 * * * *")
    monkeypatch.delenv("POD_NAMESPACE", raising=False)

    config = router_flavors.build_hook_config()

    assert config["schedule"][0]["crontab"] == "*/15 * * * *"


def test_router_flavor_hook_config_uses_full_object_filter(monkeypatch):
    """JqFilter must be '.' so cloudCredentialsRef is available at reconcile time."""
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
    monkeypatch.delenv("POD_NAMESPACE", raising=False)

    config = router_flavors.build_hook_config()

    assert config["kubernetes"][0]["jqFilter"] == "."


def test_router_flavor_hook_config_printed_on_config_flag(monkeypatch, capsys):
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
# reconcile_router_flavor — credential resolution + sync delegation
# ---------------------------------------------------------------------------


def test_reconcile_uses_cloudcredentialsref(monkeypatch):
    """Per-resource cloudCredentialsRef is used to connect to OpenStack."""
    monkeypatch.setattr(utils, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    event = {
        "object": {
            "metadata": {"name": "test-flavor"},
            "spec": {
                "name": "test-flavor",
                "driver": "some.Driver",
                "cloudCredentialsRef": {
                    "secretName": "baremetal-manage",
                    "cloudName": "understack",
                },
            },
        }
    }

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=_fake_conn(),
    ):
        with mock.patch.object(
            utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML
        ) as mock_read:
            with mock.patch("openstack_sync.hooks.router_flavors.sync_flavor"):
                router_flavors.reconcile_router_flavor(event)

    mock_read.assert_called_once_with("baremetal-manage", "clouds.yaml", "openstack")


def test_reconcile_falls_back_to_default_credentials(monkeypatch):
    """When cloudCredentialsRef is absent, operator DEFAULT_SECRET/CLOUD are used."""
    monkeypatch.setattr(utils, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_DEFAULT_SECRET", "infrasetup")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_DEFAULT_CLOUD", "understack")

    event = {
        "object": {
            "metadata": {"name": "no-ref-flavor"},
            "spec": {"name": "no-ref-flavor", "driver": "some.Driver"},
        }
    }

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=_fake_conn(),
    ):
        with mock.patch.object(
            utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML
        ) as mock_read:
            with mock.patch("openstack_sync.hooks.router_flavors.sync_flavor"):
                router_flavors.reconcile_router_flavor(event)

    mock_read.assert_called_once_with("infrasetup", "clouds.yaml", "openstack")


def test_reconcile_partial_ref_falls_back_per_field(monkeypatch):
    """A cloudCredentialsRef with only secretName still uses DEFAULT_CLOUD."""
    monkeypatch.setattr(utils, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_DEFAULT_SECRET", "infrasetup")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_DEFAULT_CLOUD", "understack")

    event = {
        "object": {
            "metadata": {"name": "partial-flavor"},
            "spec": {
                "name": "partial-flavor",
                "driver": "some.Driver",
                "cloudCredentialsRef": {"secretName": "custom-secret"},
            },
        }
    }

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=_fake_conn(),
    ):
        with mock.patch.object(
            utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML
        ) as mock_read:
            with mock.patch("openstack_sync.hooks.router_flavors.sync_flavor"):
                router_flavors.reconcile_router_flavor(event)

    mock_read.assert_called_once_with("custom-secret", "clouds.yaml", "openstack")


# ---------------------------------------------------------------------------
# main() — binding context dispatch
# ---------------------------------------------------------------------------


def test_main_dispatches_to_reconcile(monkeypatch, tmp_path):
    """main() reads BINDING_CONTEXT_PATH and dispatches each object."""
    monkeypatch.setattr(utils, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    binding_context = json.dumps(
        [
            {
                "binding": "neutron-router-flavors",
                "type": "Event",
                "watchEvent": "Added",
                "object": {
                    "metadata": {"name": "flavor-a"},
                    "spec": {
                        "name": "flavor-a",
                        "driver": "some.Driver",
                        "cloudCredentialsRef": {
                            "secretName": "infrasetup",
                            "cloudName": "understack",
                        },
                    },
                },
            }
        ]
    )

    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text(binding_context)
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=_fake_conn(),
    ):
        with mock.patch.object(utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML):
            with mock.patch(
                "openstack_sync.hooks.router_flavors.sync_flavor"
            ) as mock_sync:
                with mock.patch.object(
                    router_flavors.sys, "argv", ["router_flavors.py"]
                ):
                    result = router_flavors.main()

    assert result == 0
    mock_sync.assert_called_once()


def test_main_returns_error_on_invalid_json(monkeypatch, capsys, tmp_path):
    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text("not-json")
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]):
        result = router_flavors.main()

    assert result == 1
    assert "failed to parse binding context" in capsys.readouterr().err


def test_main_returns_zero_on_empty_context(monkeypatch, tmp_path):
    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text("")
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]):
        result = router_flavors.main()

    assert result == 0


def test_main_returns_zero_when_no_context_path(monkeypatch):
    monkeypatch.delenv("BINDING_CONTEXT_PATH", raising=False)

    with mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]):
        result = router_flavors.main()

    assert result == 0
