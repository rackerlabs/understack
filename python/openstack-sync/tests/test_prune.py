"""Tests for router flavor prune behaviour.

Pruning is gated entirely on the operator's ownership markers, so these tests
are mostly about what must *not* be deleted. Whether pruning runs at all is the
hook's decision (``config.prune``), tested in ``test_framework.py``.
"""

from __future__ import annotations

import types
from types import SimpleNamespace
from typing import Any

from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.neutron.router_flavors import markers
from openstack_sync.plugins.neutron.router_flavors import prune
from openstack_sync.plugins.neutron.router_flavors.config import SERVICE_TYPE

_DRIVER = "neutron_understack.l3_router.vrf.Vrf"


class FakeNetwork:
    """Minimal Neutron network API recording flavor and profile deletes."""

    def __init__(self, flavors: list[dict[str, Any]], profiles: dict[str, Any]):
        self._flavors = flavors
        self._profiles = profiles
        self.deleted_flavors: list[str] = []
        self.deleted_profiles: list[str] = []
        self.flavor_list_calls = 0

    def flavors(self, service_type: str | None = None) -> list[dict[str, Any]]:
        self.flavor_list_calls += 1
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
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise openstack_exceptions.NotFoundException(f"no profile {profile_id}")
        return profile

    def delete_flavor(
        self, flavor: dict[str, Any], ignore_missing: bool = True
    ) -> None:
        self.deleted_flavors.append(flavor["id"])
        self._flavors = [f for f in self._flavors if f["id"] != flavor["id"]]

    def delete_service_profile(self, profile: Any, ignore_missing: bool = True) -> None:
        profile_id = profile.id if hasattr(profile, "id") else profile["id"]
        self.deleted_profiles.append(profile_id)
        self._profiles[profile_id] = None


def _owned_profile(profile_id: str, driver: str = _DRIVER) -> Any:
    return types.SimpleNamespace(
        id=profile_id,
        driver=driver,
        meta_info=markers.managed_meta_info({"vni_alloc": "auto"}),
    )


def _owned_flavor(
    flavor_id: str, name: str, service_profile_ids: list[str] | None = None
) -> dict[str, Any]:
    return {
        "id": flavor_id,
        "name": name,
        "service_type": SERVICE_TYPE,
        "description": markers.managed_flavor_description("created by operator"),
        "service_profile_ids": list(service_profile_ids or []),
    }


def _conn(flavors: list[dict[str, Any]], profiles: dict[str, Any] | None = None) -> Any:
    return SimpleNamespace(network=FakeNetwork(flavors, profiles or {}))


# ---------------------------------------------------------------------------
# Ownership gates deletion
# ---------------------------------------------------------------------------


def test_prune_keeps_unowned_flavor_even_with_owned_profile():
    flavor = {
        "id": "manual-flavor-id",
        "name": "manual-flavor",
        "service_type": SERVICE_TYPE,
        "description": "created outside the operator",
        "service_profile_ids": ["owned-profile-id"],
    }
    profile = _owned_profile("owned-profile-id")
    conn = _conn([flavor], {profile.id: profile})

    prune.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == []


def test_prune_deletes_removed_owned_flavor():
    conn = _conn([_owned_flavor("managed-flavor-id", "removed-managed-flavor")])

    prune.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == ["managed-flavor-id"]


def test_prune_deletes_removed_flavor_and_its_unused_profile():
    profile = _owned_profile("managed-profile-id")
    flavor = _owned_flavor("managed-flavor-id", "removed-managed-flavor", [profile.id])
    conn = _conn([flavor], {profile.id: profile})

    prune.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == ["managed-flavor-id"]
    assert conn.network.deleted_profiles == ["managed-profile-id"]


# ---------------------------------------------------------------------------
# The empty-desired guard
# ---------------------------------------------------------------------------


def test_prune_keeps_owned_flavors_when_desired_list_is_empty():
    """An empty desired set may be an unreadable snapshot, not a deletion."""
    conn = _conn([_owned_flavor("managed-flavor-id", "removed-managed-flavor")])

    prune.prune_removed_flavors(conn, [])

    assert conn.network.deleted_flavors == []


def test_prune_deletes_when_empty_desired_is_authoritative():
    """A confirmed CR deletion makes the empty desired set actionable."""
    conn = _conn([_owned_flavor("managed-flavor-id", "removed-managed-flavor")])

    prune.prune_removed_flavors(conn, [], authoritative_empty=True)

    assert conn.network.deleted_flavors == ["managed-flavor-id"]


# ---------------------------------------------------------------------------
# Orphaned profile sweep
# ---------------------------------------------------------------------------


def test_prune_deletes_orphaned_owned_profile():
    """A profile whose parent flavor is already gone is collected."""
    orphan = _owned_profile("orphan-profile-id")
    conn = _conn([], {orphan.id: orphan})

    prune.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_profiles == ["orphan-profile-id"]


def test_prune_keeps_unowned_profile():
    """A profile without the ownership marker is never touched."""
    unowned = types.SimpleNamespace(
        id="unmanaged-profile-id",
        driver=_DRIVER,
        meta_info={"vni_alloc": "auto"},  # no ownership marker
    )
    conn = _conn([], {unowned.id: unowned})

    prune.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_profiles == []


def test_prune_keeps_attached_profile():
    """A profile still bound to a surviving flavor is kept."""
    attached = _owned_profile("attached-profile-id")
    kept = _owned_flavor("kept-flavor-id", "kept-flavor", [attached.id])
    conn = _conn([kept], {attached.id: attached})

    prune.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == []
    assert conn.network.deleted_profiles == []


def test_prune_lists_flavors_once_for_all_profile_checks():
    """Attachment counts come from a single flavor listing, not one per profile."""
    removed_profile = _owned_profile("removed-profile-id")
    orphan_profile = _owned_profile("orphan-profile-id")
    attached_profile = _owned_profile("attached-profile-id")
    conn = _conn(
        [
            _owned_flavor("removed-flavor-id", "removed-flavor", [removed_profile.id]),
            _owned_flavor("kept-flavor-id", "kept-flavor", [attached_profile.id]),
        ],
        {
            removed_profile.id: removed_profile,
            orphan_profile.id: orphan_profile,
            attached_profile.id: attached_profile,
        },
    )

    prune.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.flavor_list_calls == 1
    assert conn.network.deleted_flavors == ["removed-flavor-id"]
    assert conn.network.deleted_profiles == [
        "removed-profile-id",
        "orphan-profile-id",
    ]


def test_prune_skips_flavor_still_used_by_routers():
    """A flavor with routers attached is never deleted."""
    flavor = _owned_flavor("in-use-flavor-id", "removed-flavor")
    conn = _conn([flavor])
    conn.network.routers = lambda flavor_id: [{"id": "router-1"}]

    prune.prune_removed_flavors(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == []
