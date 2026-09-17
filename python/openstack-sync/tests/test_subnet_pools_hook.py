"""Tests for the subnet pool hook skeleton wiring."""

from __future__ import annotations

from typing import Any
from unittest import mock

from openstack_sync.hooks import subnet_pools as hook
from openstack_sync.hooks.framework import HookConfig

ENV_PREFIX = hook.ENV_PREFIX
BINDING_NAME = hook.BINDING_NAME


def _config(**overrides: Any) -> HookConfig:
    defaults = {
        "prefix": ENV_PREFIX,
        "crd_api_version": "neutron.understack.rackspace.net/v1alpha1",
        "crd_kind": "NeutronSubnetPool",
        "crd_resource": "neutronsubnetpools.neutron.understack.rackspace.net",
        "binding_name": BINDING_NAME,
        "namespace": "openstack",
        "status_enabled": False,
        "prune": False,
        "sync_crontab": "",
        "ready_retries": 30,
        "ready_delay": 10.0,
    }
    return HookConfig(**{**defaults, **overrides})


def test_plugin_wait_for_api_is_noop_skeleton():
    plugin = hook.SubnetPoolPlugin(_config(ready_retries=5, ready_delay=0.25))
    conn = mock.MagicMock()

    plugin.wait_for_api(conn)


def test_plugin_reconcile_reads_spec_without_openstack_calls():
    plugin = hook.SubnetPoolPlugin(_config())
    conn = mock.MagicMock()
    spec = {"name": "pool-a"}

    notes = plugin.reconcile(conn, spec, {})

    assert notes == []
    conn.assert_not_called()


def test_plugin_cleanup_policy_has_no_prune_step():
    plugin = hook.SubnetPoolPlugin(_config())

    assert not plugin.should_run_prune()
