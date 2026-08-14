"""Tests for the openstack-sync placeholder hook and shared utils."""

from __future__ import annotations

import json
from unittest import mock

import pytest

import openstack_sync.utils as utils
from openstack_sync.hooks import placeholder

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
# placeholder hook config
# ---------------------------------------------------------------------------


def test_placeholder_hook_config(capsys):
    with mock.patch.object(placeholder.sys, "argv", ["placeholder.py", "--config"]):
        assert placeholder.main() == 0

    config = json.loads(capsys.readouterr().out)
    assert config == placeholder.HOOK_CONFIG
    assert config["onStartup"] == 10


def test_placeholder_hook_run_is_noop():
    with mock.patch.object(placeholder.sys, "argv", ["placeholder.py"]):
        assert placeholder.main() == 0


# ---------------------------------------------------------------------------
# utils.read_secret_key
# ---------------------------------------------------------------------------


def test_read_secret_key_raises_on_missing_key():
    """read_secret_key propagates KeyError when the key is absent."""
    with mock.patch.object(
        utils, "read_secret_key", side_effect=KeyError("clouds.yaml")
    ):
        with pytest.raises(KeyError):
            utils.read_secret_key("infrasetup", "clouds.yaml", "openstack")


# ---------------------------------------------------------------------------
# utils.get_openstack_connection
# ---------------------------------------------------------------------------


def test_get_openstack_connection_reads_secret(monkeypatch):
    """Connection is built from the named K8s secret via read_secret_key."""
    monkeypatch.setattr(utils, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    fake_conn = mock.MagicMock(name="fake_conn")

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=fake_conn,
    ):
        with mock.patch.object(utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML):
            conn = utils.get_openstack_connection("infrasetup", "understack")

    assert conn is fake_conn


def test_get_openstack_connection_memoized(monkeypatch):
    """Same (secret_name, cloud_name) returns cached connection."""
    monkeypatch.setattr(utils, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    fake_conn = mock.MagicMock(name="fake_conn")

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=fake_conn,
    ) as mock_conn:
        with mock.patch.object(utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML):
            conn1 = utils.get_openstack_connection("infrasetup", "understack")
            conn2 = utils.get_openstack_connection("infrasetup", "understack")

    assert conn1 is conn2
    mock_conn.assert_called_once()


def test_get_openstack_connection_separate_per_secret(monkeypatch):
    """Different secrets produce independent connections."""
    monkeypatch.setattr(utils, "_connection_cache", {})
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
        with mock.patch.object(utils, "read_secret_key", side_effect=fake_read):
            result_a = utils.get_openstack_connection("infrasetup", "understack")
            result_b = utils.get_openstack_connection("baremetal-manage", "understack")

    assert result_a is conn_a
    assert result_b is conn_b


# ---------------------------------------------------------------------------
# cloudCredentialsRef resolution (shared behaviour used by all hooks)
# ---------------------------------------------------------------------------


def test_get_openstack_connection_uses_per_resource_credentials(monkeypatch):
    """Per-resource secretName/cloudName passed through to get_openstack_connection."""
    monkeypatch.setattr(utils, "_connection_cache", {})
    monkeypatch.setenv("POD_NAMESPACE", "openstack")

    fake_conn = mock.MagicMock(name="fake_conn")

    with mock.patch(
        "openstack_sync.utils.openstack.connection.Connection",
        return_value=fake_conn,
    ):
        with mock.patch.object(
            utils, "read_secret_key", return_value=FAKE_CLOUDS_YAML
        ) as mock_read:
            utils.get_openstack_connection("baremetal-manage", "understack")

    mock_read.assert_called_once_with("baremetal-manage", "clouds.yaml", "openstack")
