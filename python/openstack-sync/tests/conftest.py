"""Pytest configuration and shared fixtures for openstack-sync tests.

Sets environment variables that router_flavors_common.py reads at runtime
via env_required(). These must be present when any function that calls
crd_kind() / crd_api_version() / crd_resource() runs, so they are set
via a session-scoped autouse fixture that runs before every test.
"""

from __future__ import annotations

import pytest

_ROUTER_FLAVOR_REQUIRED_ENV = {
    "NEUTRON_ROUTER_FLAVOR_CRD_API_VERSION": (
        "neutron.understack.rackspace.net/v1alpha1"
    ),
    "NEUTRON_ROUTER_FLAVOR_CRD_KIND": "NeutronRouterFlavor",
    "NEUTRON_ROUTER_FLAVOR_CRD_RESOURCE": (
        "neutronrouterflavors.neutron.understack.rackspace.net"
    ),
}


@pytest.fixture(autouse=True)
def _router_flavor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure required router flavor env vars are set for every test.

    Individual tests may override these via their own monkeypatch calls.
    """
    for key, value in _ROUTER_FLAVOR_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
