"""Tests for Neutron router flavor prune behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from openstack_sync.plugins.neutron.router_flavors import delete_router_flavors
from openstack_sync.plugins.neutron.router_flavors import (
    router_flavors_common as common,
)


class FakeNetwork:
    def __init__(self, flavors: list[dict[str, Any]], profiles: dict[str, Any]):
        self._flavors = flavors
        self._profiles = profiles
        self.deleted_flavors: list[str] = []

    def flavors(self, service_type: str | None = None) -> list[dict[str, Any]]:
        return [
            flavor
            for flavor in self._flavors
            if service_type is None or flavor["service_type"] == service_type
        ]

    def routers(self, flavor_id: str) -> list[dict[str, Any]]:
        return []

    def get_service_profile(self, profile_id: str) -> Any:
        return self._profiles.get(profile_id)

    def delete_flavor(
        self, flavor: dict[str, Any], ignore_missing: bool = True
    ) -> None:
        self.deleted_flavors.append(flavor["id"])


def test_prune_keeps_manual_flavor_with_managed_service_profile(monkeypatch):
    monkeypatch.setattr(common, "PRUNE_REMOVED_FLAVORS", True)
    flavor = {
        "id": "manual-flavor-id",
        "name": "manual-flavor",
        "service_type": common.DEFAULT_SERVICE_TYPE,
        "description": "created outside the operator",
        "service_profile_ids": ["managed-profile-id"],
    }
    profile = SimpleNamespace(
        id="managed-profile-id",
        driver="neutron_understack.l3_router.vrf.Vrf",
        meta_info=common.managed_meta_info({"vni_alloc": "auto"}),
    )
    conn = SimpleNamespace(network=FakeNetwork([flavor], {profile.id: profile}))

    delete_router_flavors.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == []


def test_prune_keeps_managed_flavors_when_desired_list_is_empty(monkeypatch):
    monkeypatch.setattr(common, "PRUNE_REMOVED_FLAVORS", True)
    flavor = {
        "id": "managed-flavor-id",
        "name": "removed-managed-flavor",
        "service_type": common.DEFAULT_SERVICE_TYPE,
        "description": common.managed_flavor_description("created by operator"),
        "service_profile_ids": [],
    }
    conn = SimpleNamespace(network=FakeNetwork([flavor], {}))

    delete_router_flavors.prune_removed_flavors(conn, [])

    assert conn.network.deleted_flavors == []


def test_prune_deletes_removed_managed_flavor(monkeypatch):
    monkeypatch.setattr(common, "PRUNE_REMOVED_FLAVORS", True)
    flavor = {
        "id": "managed-flavor-id",
        "name": "removed-managed-flavor",
        "service_type": common.DEFAULT_SERVICE_TYPE,
        "description": common.managed_flavor_description("created by operator"),
        "service_profile_ids": [],
    }
    conn = SimpleNamespace(network=FakeNetwork([flavor], {}))

    delete_router_flavors.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == ["managed-flavor-id"]
