"""Tests for Neutron router flavor prune behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from openstack_sync.plugins.neutron.router_flavors import delete
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

    def service_profiles(self) -> list[Any]:
        return [p for p in self._profiles.values() if p is not None]

    def get_service_profile(self, profile_id: str) -> Any:
        return self._profiles.get(profile_id)

    def delete_flavor(
        self, flavor: dict[str, Any], ignore_missing: bool = True
    ) -> None:
        self.deleted_flavors.append(flavor["id"])
        self._flavors = [
            current for current in self._flavors if current["id"] != flavor["id"]
        ]


def test_prune_keeps_manual_flavor_with_managed_service_profile(monkeypatch):
    monkeypatch.setattr(delete, "PRUNE_REMOVED_FLAVORS", True)
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

    delete.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == []


def test_prune_keeps_managed_flavors_when_desired_list_is_empty(monkeypatch):
    monkeypatch.setattr(delete, "PRUNE_REMOVED_FLAVORS", True)
    flavor = {
        "id": "managed-flavor-id",
        "name": "removed-managed-flavor",
        "service_type": common.DEFAULT_SERVICE_TYPE,
        "description": common.managed_flavor_description("created by operator"),
        "service_profile_ids": [],
    }
    conn = SimpleNamespace(network=FakeNetwork([flavor], {}))

    delete.prune_removed_flavors(conn, [])

    assert conn.network.deleted_flavors == []


def test_prune_deletes_managed_flavors_when_empty_desired_is_explicit(monkeypatch):
    monkeypatch.setattr(delete, "PRUNE_REMOVED_FLAVORS", True)
    flavor = {
        "id": "managed-flavor-id",
        "name": "removed-managed-flavor",
        "service_type": common.DEFAULT_SERVICE_TYPE,
        "description": common.managed_flavor_description("created by operator"),
        "service_profile_ids": [],
    }
    conn = SimpleNamespace(network=FakeNetwork([flavor], {}))

    delete.prune_removed_flavors(conn, [], authoritative_empty_desired=True)

    assert conn.network.deleted_flavors == ["managed-flavor-id"]


def test_prune_deletes_removed_managed_flavor(monkeypatch):
    monkeypatch.setattr(delete, "PRUNE_REMOVED_FLAVORS", True)
    flavor = {
        "id": "managed-flavor-id",
        "name": "removed-managed-flavor",
        "service_type": common.DEFAULT_SERVICE_TYPE,
        "description": common.managed_flavor_description("created by operator"),
        "service_profile_ids": [],
    }
    conn = SimpleNamespace(network=FakeNetwork([flavor], {}))

    delete.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == ["managed-flavor-id"]


def test_prune_deletes_removed_managed_flavor_and_unused_profile(monkeypatch):
    monkeypatch.setattr(delete, "PRUNE_REMOVED_FLAVORS", True)
    monkeypatch.setattr(delete, "DELETE_UNUSED_SERVICE_PROFILES", True)
    profile = _make_orphan_profile("managed-profile-id")
    flavor = {
        "id": "managed-flavor-id",
        "name": "removed-managed-flavor",
        "service_type": common.DEFAULT_SERVICE_TYPE,
        "description": common.managed_flavor_description("created by operator"),
        "service_profile_ids": [profile.id],
    }
    network = FakeNetworkWithProfiles([flavor], {profile.id: profile})
    conn = SimpleNamespace(network=network)

    delete.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert network.deleted_flavors == ["managed-flavor-id"]
    assert network.deleted_profiles == ["managed-profile-id"]


# ---------------------------------------------------------------------------
# prune_orphaned_service_profiles: second-pass GC for partial-failure orphans
# ---------------------------------------------------------------------------


class FakeNetworkWithProfiles(FakeNetwork):
    """FakeNetwork extended to track service profile deletes."""

    def __init__(
        self,
        flavors: list[dict[str, Any]],
        profiles: dict[str, Any],
    ):
        super().__init__(flavors, profiles)
        self.deleted_profiles: list[str] = []

    def service_profiles(self) -> list[Any]:
        return [p for p in self._profiles.values() if p is not None]

    def delete_service_profile(self, profile: Any, ignore_missing: bool = True) -> None:
        profile_id = profile.id if hasattr(profile, "id") else profile["id"]
        self.deleted_profiles.append(profile_id)
        self._profiles[profile_id] = None

    def get_service_profile(self, profile_id: str) -> Any:
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise Exception(f"Profile {profile_id} not found")
        return profile


def _make_orphan_profile(
    profile_id: str, driver: str = "neutron_understack.l3_router.vrf.Vrf"
):
    """Return a SimpleNamespace service profile with operator ownership markers."""
    import types

    return types.SimpleNamespace(
        id=profile_id,
        driver=driver,
        meta_info=common.managed_meta_info({"vni_alloc": "auto"}),
    )


def test_prune_orphaned_profiles_deletes_unattached_managed_profile(monkeypatch):
    """A managed profile with no parent flavor is deleted by the second pass."""
    monkeypatch.setattr(delete, "PRUNE_REMOVED_FLAVORS", True)
    monkeypatch.setattr(delete, "DELETE_UNUSED_SERVICE_PROFILES", True)

    orphan = _make_orphan_profile("orphan-profile-id")
    # No flavors in Neutron; the orphan's parent was already deleted.
    network = FakeNetworkWithProfiles(flavors=[], profiles={orphan.id: orphan})
    conn = SimpleNamespace(network=network)

    delete.prune_orphaned_service_profiles(conn, set(), {})

    assert "orphan-profile-id" in network.deleted_profiles


def test_prune_orphaned_profiles_keeps_protected_profile(monkeypatch):
    """A profile listed in protected_profile_ids is never deleted."""
    monkeypatch.setattr(delete, "DELETE_UNUSED_SERVICE_PROFILES", True)

    orphan = _make_orphan_profile("protected-profile-id")
    network = FakeNetworkWithProfiles(flavors=[], profiles={orphan.id: orphan})
    conn = SimpleNamespace(network=network)

    delete.prune_orphaned_service_profiles(conn, {"protected-profile-id"}, {})

    assert network.deleted_profiles == []


def test_prune_orphaned_profiles_keeps_non_managed_profile(monkeypatch):
    """A profile without the operator ownership marker is not touched."""
    monkeypatch.setattr(delete, "DELETE_UNUSED_SERVICE_PROFILES", True)
    import types

    unmanaged = types.SimpleNamespace(
        id="unmanaged-profile-id",
        driver="neutron_understack.l3_router.vrf.Vrf",
        meta_info={"vni_alloc": "auto"},  # no MANAGED_META_INFO_KEY
    )
    network = FakeNetworkWithProfiles(flavors=[], profiles={unmanaged.id: unmanaged})
    conn = SimpleNamespace(network=network)

    delete.prune_orphaned_service_profiles(conn, set(), {})

    assert network.deleted_profiles == []


def test_prune_removed_flavors_cleans_up_orphaned_profile_on_next_run(monkeypatch):
    """Simulate a partial failure: flavor deleted, profile cleanup threw last run.

    On the next prune_removed_flavors call the flavor no longer exists in
    Neutron, so the flavor loop skips it.  The second-pass GC should find and
    delete the orphaned profile.
    """
    monkeypatch.setattr(delete, "PRUNE_REMOVED_FLAVORS", True)
    monkeypatch.setattr(delete, "DELETE_UNUSED_SERVICE_PROFILES", True)

    # Neutron state after the partial failure: flavor is gone, profile remains.
    orphan = _make_orphan_profile("orphan-after-partial-failure")
    network = FakeNetworkWithProfiles(flavors=[], profiles={orphan.id: orphan})
    conn = SimpleNamespace(network=network)

    # desired list is non-empty so the empty-list guard does not fire.
    delete.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert "orphan-after-partial-failure" in network.deleted_profiles
