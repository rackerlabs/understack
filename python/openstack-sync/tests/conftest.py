"""Pytest configuration and shared fixtures for openstack-sync tests.

Two levels of configuration, matching where the code reads it:

* Hook-level tests drive ``main()``, which reads the environment the Helm chart
  injects. The autouse fixture below provides the CRD identity variables the
  chart always sets, so those tests exercise the real boundary.
* Everything below the hook takes a :class:`HookConfig` argument, so unit tests
  use the ``hook_config`` fixture and never touch the environment.
"""

from __future__ import annotations

import pytest

from openstack_sync.hooks.framework import HookConfig
from openstack_sync.plugins.neutron.router_flavors.config import BINDING_NAME
from openstack_sync.plugins.neutron.router_flavors.config import ENV_PREFIX

CRD_API_VERSION = "neutron.understack.rackspace.net/v1alpha1"
CRD_KIND = "NeutronRouterFlavor"
CRD_RESOURCE = "neutronrouterflavors.neutron.understack.rackspace.net"

_CRD_IDENTITY_ENV = {
    f"{ENV_PREFIX}_CRD_API_VERSION": CRD_API_VERSION,
    f"{ENV_PREFIX}_CRD_KIND": CRD_KIND,
    f"{ENV_PREFIX}_CRD_RESOURCE": CRD_RESOURCE,
}


@pytest.fixture(autouse=True)
def _crd_identity_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide the CRD identity variables the Helm chart always injects.

    Individual tests may override these with their own monkeypatch calls.
    """
    for key, value in _CRD_IDENTITY_ENV.items():
        monkeypatch.setenv(key, value)


def make_hook_config(**overrides) -> HookConfig:
    """Build a HookConfig without touching the environment."""
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


@pytest.fixture
def hook_config() -> HookConfig:
    return make_hook_config()
