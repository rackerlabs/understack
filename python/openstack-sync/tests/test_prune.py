"""Tests for router flavor prune behaviour.

Deletion is gated on the ownership markers, so most of these cover what must
*not* be deleted. Whether prune runs at all is tested in ``test_framework.py``.
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
        self.profile_get_calls = 0

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
        self.profile_get_calls += 1
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


def _prune(
    conn: Any,
    desired: list[dict[str, Any]],
    deleted: list[dict[str, Any]] | None = None,
    *,
    sweep_unseen: bool = True,
) -> None:
    prune.prune_removed_flavors(
        conn,
        desired,
        deleted_specs=deleted if deleted is not None else [],
        sweep_unseen=sweep_unseen,
    )


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

    _prune(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == []


def test_prune_deletes_removed_owned_flavor():
    conn = _conn([_owned_flavor("managed-flavor-id", "removed-managed-flavor")])

    _prune(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == ["managed-flavor-id"]


def test_prune_deletes_removed_flavor_and_its_unused_profile():
    profile = _owned_profile("managed-profile-id")
    flavor = _owned_flavor("managed-flavor-id", "removed-managed-flavor", [profile.id])
    conn = _conn([flavor], {profile.id: profile})

    _prune(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == ["managed-flavor-id"]
    assert conn.network.deleted_profiles == ["managed-profile-id"]


# ---------------------------------------------------------------------------
# The empty-desired guard
# ---------------------------------------------------------------------------


def test_prune_keeps_owned_flavors_when_desired_list_is_empty():
    """An empty desired set may be an unreadable snapshot, not a deletion."""
    conn = _conn([_owned_flavor("managed-flavor-id", "removed-managed-flavor")])

    _prune(conn, [])

    assert conn.network.deleted_flavors == []


def test_prune_deletes_only_the_named_deleted_flavors_without_a_desired_set():
    """Without a desired set to diff, only the lost CRs may be acted on."""
    conn = _conn(
        [
            _owned_flavor("managed-flavor-id", "removed-managed-flavor"),
            _owned_flavor("unrelated-flavor-id", "unrelated-flavor"),
        ]
    )

    _prune(conn, [], [{"name": "removed-managed-flavor"}])

    assert conn.network.deleted_flavors == ["managed-flavor-id"]


def test_prune_keeps_a_deleted_flavor_another_cr_still_wants():
    """The desired set wins over a deletion naming the same flavor."""
    conn = _conn([_owned_flavor("shared-flavor-id", "shared-flavor")])

    _prune(conn, [{"name": "shared-flavor"}], [{"name": "shared-flavor"}])

    assert conn.network.deleted_flavors == []


# ---------------------------------------------------------------------------
# A withheld sweep
# ---------------------------------------------------------------------------


def test_prune_without_the_sweep_deletes_only_what_was_deleted():
    """With sweeping off, a desired set is a protection list and nothing more.

    The framework withholds the sweep when a CR failed to reconcile, so the
    desired set may be missing names. An owned flavor absent from it is left
    alone; only the flavors a deletion names go.
    """
    conn = _conn(
        [
            _owned_flavor("gone-flavor-id", "gone-flavor"),
            _owned_flavor("unnamed-flavor-id", "absent-from-desired"),
        ]
    )

    _prune(
        conn,
        [{"name": "kept-flavor"}],
        [{"name": "gone-flavor"}],
        sweep_unseen=False,
    )

    assert conn.network.deleted_flavors == ["gone-flavor-id"]


def test_prune_without_the_sweep_still_protects_the_desired_set():
    """A deletion cannot remove a flavor the desired set still names.

    This is what makes deleting by name safe while a reconcile is failing: the
    failing CR is still in the desired set, so it cannot be deleted.
    """
    conn = _conn([_owned_flavor("shared-flavor-id", "shared-flavor")])

    _prune(
        conn,
        [{"name": "shared-flavor"}],
        [{"name": "shared-flavor"}],
        sweep_unseen=False,
    )

    assert conn.network.deleted_flavors == []


def test_prune_without_the_sweep_and_nothing_deleted_does_nothing():
    conn = _conn([_owned_flavor("managed-flavor-id", "removed-managed-flavor")])

    _prune(conn, [{"name": "kept-flavor"}], [], sweep_unseen=False)

    assert conn.network.deleted_flavors == []
    assert conn.network.deleted_profiles == []


# ---------------------------------------------------------------------------
# Orphaned profile sweep
# ---------------------------------------------------------------------------


def test_prune_deletes_orphaned_owned_profile():
    """A profile whose parent flavor is already gone is collected."""
    orphan = _owned_profile("orphan-profile-id")
    conn = _conn([], {orphan.id: orphan})

    _prune(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_profiles == ["orphan-profile-id"]


def test_prune_keeps_unowned_profile():
    """A profile without the ownership marker is never touched."""
    unowned = types.SimpleNamespace(
        id="unmanaged-profile-id",
        driver=_DRIVER,
        meta_info={"vni_alloc": "auto"},  # no ownership marker
    )
    conn = _conn([], {unowned.id: unowned})

    _prune(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_profiles == []


def test_prune_keeps_attached_profile():
    """A profile still bound to a surviving flavor is kept."""
    attached = _owned_profile("attached-profile-id")
    kept = _owned_flavor("kept-flavor-id", "kept-flavor", [attached.id])
    conn = _conn([kept], {attached.id: attached})

    _prune(conn, [{"name": "kept-flavor"}])

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

    _prune(conn, [{"name": "kept-flavor"}])

    assert conn.network.flavor_list_calls == 1
    # Only the deleted flavor's profile needs a GET; the orphan came from the
    # sweep's own listing.
    assert conn.network.profile_get_calls == 1
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

    _prune(conn, [{"name": "kept-flavor"}])

    assert conn.network.deleted_flavors == []


# ---------------------------------------------------------------------------
# The orphaned profile sweep on its own, with PRUNE off
# ---------------------------------------------------------------------------


def test_prune_orphaned_profiles_deletes_an_owned_unattached_profile():
    orphan = _owned_profile("orphan-profile-id")
    conn = _conn([], {orphan.id: orphan})

    prune.prune_orphaned_profiles(conn)

    assert conn.network.deleted_profiles == ["orphan-profile-id"]


def test_prune_orphaned_profiles_keeps_an_unowned_profile():
    unowned = SimpleNamespace(
        id="unmanaged-profile-id",
        driver=_DRIVER,
        meta_info={"vni_alloc": "auto"},  # no ownership marker
    )
    conn = _conn([], {unowned.id: unowned})

    prune.prune_orphaned_profiles(conn)

    assert conn.network.deleted_profiles == []


def test_prune_orphaned_profiles_keeps_an_attached_profile():
    """The sweep needs its own attachment counts, or it deletes a bound profile."""
    attached = _owned_profile("attached-profile-id")
    kept = _owned_flavor("kept-flavor-id", "kept-flavor", [attached.id])
    conn = _conn([kept], {attached.id: attached})

    prune.prune_orphaned_profiles(conn)

    assert conn.network.deleted_profiles == []


def test_prune_orphaned_profiles_reuses_the_listing_instead_of_refetching():
    """The sweep already holds the profile, so it must not GET it again."""
    orphan = _owned_profile("orphan-profile-id")
    conn = _conn([], {orphan.id: orphan})

    prune.prune_orphaned_profiles(conn)

    assert conn.network.profile_get_calls == 0
    assert conn.network.deleted_profiles == ["orphan-profile-id"]


def test_prune_orphaned_profiles_deletes_no_flavor():
    """The sweep must not delete a flavor; that still needs PRUNE."""
    orphan = _owned_profile("orphan-profile-id")
    conn = _conn(
        [_owned_flavor("removed-flavor-id", "removed-flavor")],
        {orphan.id: orphan},
    )

    prune.prune_orphaned_profiles(conn)

    assert conn.network.deleted_flavors == []
    assert conn.network.deleted_profiles == ["orphan-profile-id"]
