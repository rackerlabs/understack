"""Pytest configuration and shared fixtures for openstack-sync tests.

Sets environment variables that router_flavors_common.py reads at import time
(os.environ[...] fail-fast vars). These must be present before the module is
first imported, so they are set at collection time via a session-scoped
autouse fixture.
"""

from __future__ import annotations

import os

import pytest

# ---------------------------------------------------------------------------
# Required env vars for router_flavors_common - set before any import
# ---------------------------------------------------------------------------

_ROUTER_FLAVOR_REQUIRED_ENV = {
    "NEUTRON_ROUTER_FLAVOR_CRD_API_VERSION": (
        "neutron.understack.rackspace.net/v1alpha1"
    ),
    "NEUTRON_ROUTER_FLAVOR_CRD_KIND": "NeutronRouterFlavor",
    "NEUTRON_ROUTER_FLAVOR_CRD_RESOURCE": (
        "neutronrouterflavors.neutron.understack.rackspace.net"
    ),
}

for _key, _value in _ROUTER_FLAVOR_REQUIRED_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True)
def _router_flavor_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure required router flavor env vars are set for every test.

    Individual tests may override these via their own monkeypatch calls.
    """
    for key, value in _ROUTER_FLAVOR_REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
