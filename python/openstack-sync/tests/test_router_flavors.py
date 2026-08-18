"""Tests for the Neutron router flavors hook."""

from __future__ import annotations

import json
from unittest import mock

import pytest

import openstack_sync.utils as k8s_module
from openstack_sync.hooks import router_flavors

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def clear_router_flavor_env(monkeypatch):
    monkeypatch.delenv("NEUTRON_ROUTER_FLAVOR_ENABLED", raising=False)
    monkeypatch.delenv("NEUTRON_ROUTER_FLAVOR_NAMESPACE", raising=False)
    monkeypatch.delenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", raising=False)
    monkeypatch.delenv("POD_NAMESPACE", raising=False)


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


# ---------------------------------------------------------------------------
# build_hook_config
# ---------------------------------------------------------------------------


def test_router_flavor_hook_config_disabled(monkeypatch):
    clear_router_flavor_env(monkeypatch)

    config = router_flavors.build_hook_config()

    assert config["onStartup"] == 10
    assert "kubernetes" not in config
    assert "schedule" not in config


def test_router_flavor_hook_config_uses_pod_namespace(monkeypatch):
    clear_router_flavor_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    config = router_flavors.build_hook_config()

    kubernetes_binding = config["kubernetes"][0]
    assert kubernetes_binding["namespace"] == {
        "nameSelector": {
            "matchNames": ["openstack"],
        },
    }
    assert config["schedule"][0]["crontab"] == "0 * * * *"
    assert "onStartup" not in config


def test_router_flavor_hook_config_namespace_override(monkeypatch):
    clear_router_flavor_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_NAMESPACE", "custom")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    config = router_flavors.build_hook_config()

    kubernetes_binding = config["kubernetes"][0]
    assert kubernetes_binding["namespace"]["nameSelector"]["matchNames"] == ["custom"]


def test_router_flavor_hook_config_output_uses_runtime_environment(monkeypatch, capsys):
    clear_router_flavor_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")
    monkeypatch.setenv("POD_NAMESPACE", "openstack")
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "*/15 * * * *")

    with mock.patch.object(
        router_flavors.sys, "argv", ["router_flavors.py", "--config"]
    ):
        assert router_flavors.main() == 0

    config = json.loads(capsys.readouterr().out)
    assert config["kubernetes"][0]["namespace"]["nameSelector"]["matchNames"] == [
        "openstack"
    ]
    assert config["schedule"][0]["crontab"] == "*/15 * * * *"


def test_router_flavor_hook_config_uses_full_object_filter(monkeypatch):
    """JqFilter must be '.' so cloudCredentialsRef is available in the event."""
    clear_router_flavor_env(monkeypatch)
    monkeypatch.setenv("NEUTRON_ROUTER_FLAVOR_ENABLED", "true")

    config = router_flavors.build_hook_config()

    assert config["kubernetes"][0]["jqFilter"] == "."


# ---------------------------------------------------------------------------
# k8s.read_secret_key (common module)
# ---------------------------------------------------------------------------


def test_read_secret_key_raises_on_missing_key():
    """read_secret_key propagates KeyError when the key is absent."""
    with mock.patch.object(
        k8s_module, "read_secret_key", side_effect=KeyError("clouds.yaml")
    ):
        with pytest.raises(KeyError):
            k8s_module.read_secret_key("infrasetup", "clouds.yaml", "openstack")


# ---------------------------------------------------------------------------
# k8s.get_openstack_connection (common module, used by all hooks)
# ---------------------------------------------------------------------------


def test_get_openstack_connection_reads_secret(monkeypatch):
    """Connection is built from the named K8s secret via read_secret_key."""
    monkeypatch.setattr(k8s_module, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    fake_conn = mock.MagicMock(name="fake_conn")

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=fake_conn,
    ):
        with mock.patch.object(
            k8s_module, "read_secret_key", return_value=FAKE_CLOUDS_YAML
        ):
            conn = k8s_module.get_openstack_connection("infrasetup", "understack")

    assert conn is fake_conn


def test_get_openstack_connection_memoized(monkeypatch):
    """Same (secret_name, cloud_name) returns cached connection."""
    monkeypatch.setattr(k8s_module, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    fake_conn = mock.MagicMock(name="fake_conn")

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=fake_conn,
    ) as mock_conn:
        with mock.patch.object(
            k8s_module, "read_secret_key", return_value=FAKE_CLOUDS_YAML
        ):
            conn1 = k8s_module.get_openstack_connection("infrasetup", "understack")
            conn2 = k8s_module.get_openstack_connection("infrasetup", "understack")

    assert conn1 is conn2
    mock_conn.assert_called_once()


def test_get_openstack_connection_separate_per_secret(monkeypatch):
    """Different secrets produce independent connections."""
    monkeypatch.setattr(k8s_module, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    conn_a = mock.MagicMock(name="conn_a")
    conn_b = mock.MagicMock(name="conn_b")

    bm_yaml = FAKE_CLOUDS_YAML.replace("infrasetup", "baremetal-manage")

    def fake_read(secret_name, secret_key, namespace):
        return FAKE_CLOUDS_YAML if secret_name == "infrasetup" else bm_yaml  # noqa: S105

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        side_effect=[conn_a, conn_b],
    ):
        with mock.patch.object(k8s_module, "read_secret_key", side_effect=fake_read):
            result_a = k8s_module.get_openstack_connection("infrasetup", "understack")
            result_b = k8s_module.get_openstack_connection(
                "baremetal-manage", "understack"
            )

    assert result_a is conn_a
    assert result_b is conn_b


# ---------------------------------------------------------------------------
# reconcile_router_flavor
# ---------------------------------------------------------------------------


def test_reconcile_router_flavor_reads_credentials_ref(monkeypatch):
    """Hook reads secretName + cloudName from spec.cloudCredentialsRef."""
    monkeypatch.setattr(k8s_module, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    fake_conn = mock.MagicMock()

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
        return_value=fake_conn,
    ):
        with mock.patch.object(
            k8s_module, "read_secret_key", return_value=FAKE_CLOUDS_YAML
        ) as mock_read:
            router_flavors.reconcile_router_flavor(event)

    mock_read.assert_called_once_with("baremetal-manage", "clouds.yaml", "openstack")


def test_reconcile_router_flavor_raises_when_creds_ref_missing():
    """Missing cloudCredentialsRef raises ValueError."""
    event = {
        "object": {
            "metadata": {"name": "bad-flavor"},
            "spec": {"name": "bad-flavor", "driver": "some.Driver"},
        }
    }

    with pytest.raises(ValueError, match="cloudCredentialsRef"):
        router_flavors.reconcile_router_flavor(event)


def test_reconcile_router_flavor_raises_when_secret_name_missing():
    event = {
        "object": {
            "metadata": {"name": "bad-flavor"},
            "spec": {
                "name": "bad-flavor",
                "driver": "some.Driver",
                "cloudCredentialsRef": {"cloudName": "understack"},
            },
        }
    }

    with pytest.raises(ValueError, match="cloudCredentialsRef"):
        router_flavors.reconcile_router_flavor(event)


def test_reconcile_router_flavor_raises_when_cloud_name_missing():
    event = {
        "object": {
            "metadata": {"name": "bad-flavor"},
            "spec": {
                "name": "bad-flavor",
                "driver": "some.Driver",
                "cloudCredentialsRef": {"secretName": "baremetal-manage"},
            },
        }
    }

    with pytest.raises(ValueError, match="cloudCredentialsRef"):
        router_flavors.reconcile_router_flavor(event)


# ---------------------------------------------------------------------------
# main() — binding context dispatch
# ---------------------------------------------------------------------------


def test_main_dispatches_binding_context(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(k8s_module, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    fake_conn = mock.MagicMock()

    binding_context = json.dumps(
        [
            {
                "binding": "neutron-router-flavors",
                "objects": [
                    {
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
                        }
                    }
                ],
            }
        ]
    )

    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text(binding_context)
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=fake_conn,
    ):
        with mock.patch.object(
            k8s_module, "read_secret_key", return_value=FAKE_CLOUDS_YAML
        ):
            with mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]):
                result = router_flavors.main()

    assert result == 0


def test_main_returns_error_on_invalid_json(monkeypatch, capsys, tmp_path):
    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text("not-json")
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]):
        result = router_flavors.main()

    assert result == 1
    assert "failed to parse binding context" in capsys.readouterr().err


def test_main_returns_zero_on_empty_stdin(monkeypatch, tmp_path):
    ctx_file = tmp_path / "binding_context.json"
    ctx_file.write_text("")
    monkeypatch.setenv("BINDING_CONTEXT_PATH", str(ctx_file))

    with mock.patch.object(router_flavors.sys, "argv", ["router_flavors.py"]):
        result = router_flavors.main()

    assert result == 0
