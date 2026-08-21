"""Tests for create.py helpers: ensure_profile and reconcile_flavor_profiles."""

from __future__ import annotations

import types
from typing import Any
from unittest import mock

from openstack_sync.plugins import common as plugin_common
from openstack_sync.plugins.neutron.router_flavors import create
from openstack_sync.plugins.neutron.router_flavors import (
    router_flavors_common as common,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    profile_id: str,
    driver: str = "neutron_understack.l3_router.vrf.Vrf",
    meta_info: Any = None,
    managed: bool = True,
    is_enabled: bool = True,
) -> Any:
    raw_meta = dict(meta_info or {})
    if managed:
        raw_meta.update(common.operator_meta_info_markers())
    return types.SimpleNamespace(
        id=profile_id,
        driver=driver,
        is_enabled=is_enabled,
        meta_info=plugin_common.meta_info_payload(raw_meta),
    )


def _make_flavor(
    flavor_id: str = "flavor-id",
    name: str = "test-flavor",
    service_profile_ids: list[str] | None = None,
) -> Any:
    return types.SimpleNamespace(
        id=flavor_id,
        name=name,
        service_profile_ids=list(service_profile_ids or []),
    )


def _profile_spec(
    driver: str = "neutron_understack.l3_router.vrf.Vrf",
    description: str = "desc",
    meta_info: dict[str, Any] | None = None,
    is_enabled: bool = True,
) -> dict[str, Any]:
    return {
        "driver": driver,
        "description": description,
        "meta_info": meta_info if meta_info is not None else {},
        "is_enabled": is_enabled,
    }


# ---------------------------------------------------------------------------
# service profile query cache
# ---------------------------------------------------------------------------


def test_list_service_profiles_queries_by_driver():
    network = mock.MagicMock()
    network.service_profiles.return_value = [_make_profile("profile-id")]
    conn = types.SimpleNamespace(network=network)

    result = create.list_service_profiles(conn, "some.Driver")

    assert result == list(network.service_profiles.return_value)
    network.service_profiles.assert_called_once_with(driver="some.Driver")


def test_service_profiles_for_driver_caches_per_driver():
    first_driver = "first.Driver"
    second_driver = "second.Driver"
    first_profile = _make_profile("first-profile", driver=first_driver)
    second_profile = _make_profile("second-profile", driver=second_driver)
    network = mock.MagicMock()
    network.service_profiles.side_effect = [[first_profile], [second_profile]]
    conn = types.SimpleNamespace(network=network)
    profile_cache: create.ServiceProfileCache = {}

    first_result = create.service_profiles_for_driver(conn, first_driver, profile_cache)
    cached_result = create.service_profiles_for_driver(
        conn, first_driver, profile_cache
    )
    second_result = create.service_profiles_for_driver(
        conn, second_driver, profile_cache
    )

    assert first_result == [first_profile]
    assert cached_result is first_result
    assert second_result == [second_profile]
    assert network.service_profiles.call_args_list == [
        mock.call(driver=first_driver),
        mock.call(driver=second_driver),
    ]


# ---------------------------------------------------------------------------
# ensure_profile: create-or-reuse by (driver, meta_info)
# ---------------------------------------------------------------------------


def test_ensure_profile_creates_service_profile_with_management_markers():
    network = mock.MagicMock()
    network.service_profiles.return_value = []
    network.create_service_profile.return_value = _make_profile("new-profile")
    conn = types.SimpleNamespace(network=network)

    create.ensure_profile(
        conn,
        flavor_name="test-flavor",
        profile_spec=_profile_spec(meta_info={"vni_alloc": "auto"}),
        profile_cache={},
    )

    kwargs = conn.network.create_service_profile.call_args.kwargs
    assert kwargs["driver"] == "neutron_understack.l3_router.vrf.Vrf"
    assert kwargs["is_enabled"] is True
    meta_info = plugin_common.normalize_meta_info(kwargs["meta_info"])
    assert meta_info["vni_alloc"] == "auto"
    for key, value in common.operator_meta_info_markers().items():
        assert meta_info[key] == value


def test_ensure_profile_creates_disabled_profile_when_spec_disables():
    network = mock.MagicMock()
    network.service_profiles.return_value = []
    network.create_service_profile.return_value = _make_profile(
        "new-profile", is_enabled=False
    )
    conn = types.SimpleNamespace(network=network)

    create.ensure_profile(
        conn,
        flavor_name="test-flavor",
        profile_spec=_profile_spec(is_enabled=False),
        profile_cache={},
    )

    assert conn.network.create_service_profile.call_args.kwargs["is_enabled"] is False


def test_ensure_profile_reuses_existing_matching_profile():
    """When Neutron already has a managed profile matching (driver, meta_info)."""
    meta_info = {"vni_alloc": "auto"}
    existing = _make_profile("existing-profile", meta_info=meta_info, managed=True)
    network = mock.MagicMock()
    network.service_profiles.return_value = [existing]
    conn = types.SimpleNamespace(network=network)

    result = create.ensure_profile(
        conn,
        flavor_name="test-flavor",
        profile_spec=_profile_spec(meta_info=meta_info),
        profile_cache={},
    )

    assert result is existing
    conn.network.create_service_profile.assert_not_called()


def test_ensure_profile_appends_newly_created_profile_to_driver_cache():
    """A profile created for one flavor must be visible to the next flavor.

    profile_cache is caller-owned and shared across all flavors in the same
    credential group during one reconcile pass. Two flavors with an identical
    ``(driver, meta_info)`` spec must share one profile rather than each
    creating a duplicate.
    """
    driver = "some.Driver"
    meta_info = {"vni_alloc": "auto"}
    created_profile = _make_profile("new-profile", driver=driver, meta_info=meta_info)
    network = mock.MagicMock()
    network.service_profiles.return_value = []
    network.create_service_profile.return_value = created_profile
    conn = types.SimpleNamespace(network=network)
    profile_cache: create.ServiceProfileCache = {}

    created = create.ensure_profile(
        conn,
        flavor_name="flavor-a",
        profile_spec=_profile_spec(driver=driver, meta_info=meta_info),
        profile_cache=profile_cache,
    )
    reused = create.ensure_profile(
        conn,
        flavor_name="flavor-b",
        profile_spec=_profile_spec(driver=driver, meta_info=meta_info),
        profile_cache=profile_cache,
    )

    assert created is created_profile
    assert reused is created
    conn.network.create_service_profile.assert_called_once()
    conn.network.service_profiles.assert_called_once_with(driver=driver)


def test_ensure_profile_does_not_reuse_profiles_across_drivers():
    meta_info = {"vni_alloc": "auto"}
    first_driver = "first.Driver"
    second_driver = "second.Driver"
    first_profile = _make_profile(
        "first-profile", driver=first_driver, meta_info=meta_info
    )
    second_profile = _make_profile(
        "second-profile", driver=second_driver, meta_info=meta_info
    )
    network = mock.MagicMock()
    network.service_profiles.side_effect = [[], []]
    network.create_service_profile.side_effect = [first_profile, second_profile]
    conn = types.SimpleNamespace(network=network)
    profile_cache: create.ServiceProfileCache = {}

    first_result = create.ensure_profile(
        conn,
        flavor_name="flavor-a",
        profile_spec=_profile_spec(driver=first_driver, meta_info=meta_info),
        profile_cache=profile_cache,
    )
    second_result = create.ensure_profile(
        conn,
        flavor_name="flavor-b",
        profile_spec=_profile_spec(driver=second_driver, meta_info=meta_info),
        profile_cache=profile_cache,
    )

    assert first_result is first_profile
    assert second_result is second_profile
    assert network.create_service_profile.call_count == 2


# ---------------------------------------------------------------------------
# reconcile_flavor_profiles: set-based associate + disassociate-if-managed
# ---------------------------------------------------------------------------


def _reconcile_conn(
    flavor: Any, disassociate_profile_lookup: dict[str, Any] | None = None
) -> Any:
    """Build a connection mock whose network exposes these behaviors.

    * ``get_flavor`` returns *flavor* on every call
    * ``associate_flavor_with_service_profile`` succeeds silently
    * ``disassociate_flavor_from_service_profile`` succeeds silently
    * ``get_service_profile`` returns matching profile from
      *disassociate_profile_lookup* so ``is_managed_service_profile`` can be
      evaluated on candidates for removal.
    """
    lookup = disassociate_profile_lookup or {}
    network = mock.MagicMock()
    network.get_flavor.return_value = flavor
    network.get_service_profile.side_effect = lambda pid: lookup.get(pid)
    return types.SimpleNamespace(network=network)


def test_reconcile_flavor_profiles_no_op_when_matches():
    """Current == desired → no associate/disassociate calls."""
    flavor = _make_flavor(service_profile_ids=["prof-a", "prof-b"])
    desired = [
        _make_profile("prof-a"),
        _make_profile("prof-b"),
    ]
    conn = _reconcile_conn(flavor)

    result = create.reconcile_flavor_profiles(conn, flavor, desired)

    conn.network.associate_flavor_with_service_profile.assert_not_called()
    conn.network.disassociate_flavor_from_service_profile.assert_not_called()
    assert result is flavor


def test_reconcile_flavor_profiles_associates_missing():
    flavor = _make_flavor(service_profile_ids=[])
    desired = [_make_profile("prof-a"), _make_profile("prof-b")]
    conn = _reconcile_conn(flavor)

    create.reconcile_flavor_profiles(conn, flavor, desired)

    associate_calls = conn.network.associate_flavor_with_service_profile.call_args_list
    associated_ids = sorted(call.args[1].id for call in associate_calls)
    assert associated_ids == ["prof-a", "prof-b"]
    conn.network.disassociate_flavor_from_service_profile.assert_not_called()


def test_reconcile_flavor_profiles_disassociates_managed_extra():
    """A managed profile currently on the flavor but not desired must be unbound."""
    flavor = _make_flavor(service_profile_ids=["prof-a", "prof-extra"])
    desired = [_make_profile("prof-a")]
    extra_profile = _make_profile("prof-extra", managed=True)
    conn = _reconcile_conn(flavor, {"prof-extra": extra_profile})

    create.reconcile_flavor_profiles(conn, flavor, desired)

    conn.network.associate_flavor_with_service_profile.assert_not_called()
    conn.network.disassociate_flavor_from_service_profile.assert_called_once()
    call = conn.network.disassociate_flavor_from_service_profile.call_args
    assert call.args[1] is extra_profile


def test_reconcile_flavor_profiles_keeps_unmanaged_extra():
    """An unmanaged profile attached out-of-band must not be disassociated."""
    flavor = _make_flavor(service_profile_ids=["prof-a", "prof-adhoc"])
    desired = [_make_profile("prof-a")]
    unmanaged = _make_profile("prof-adhoc", managed=False)
    conn = _reconcile_conn(flavor, {"prof-adhoc": unmanaged})

    create.reconcile_flavor_profiles(conn, flavor, desired)

    conn.network.disassociate_flavor_from_service_profile.assert_not_called()


def test_reconcile_flavor_profiles_handles_add_and_remove_together():
    """Simultaneous associate + disassociate in one reconcile pass."""
    flavor = _make_flavor(service_profile_ids=["prof-old"])
    desired = [_make_profile("prof-new")]
    old_profile = _make_profile("prof-old", managed=True)
    conn = _reconcile_conn(flavor, {"prof-old": old_profile})

    create.reconcile_flavor_profiles(conn, flavor, desired)

    conn.network.associate_flavor_with_service_profile.assert_called_once()
    associate_call = conn.network.associate_flavor_with_service_profile.call_args
    assert associate_call.args[1].id == "prof-new"
    conn.network.disassociate_flavor_from_service_profile.assert_called_once()
    disassociate_call = conn.network.disassociate_flavor_from_service_profile.call_args
    assert disassociate_call.args[1] is old_profile


def test_reconcile_flavor_profiles_skips_deleted_extra_profile():
    """A candidate for disassociation that no longer exists is a silent no-op."""
    flavor = _make_flavor(service_profile_ids=["prof-a", "prof-gone"])
    desired = [_make_profile("prof-a")]
    # Neutron says prof-gone doesn't exist anymore.
    conn = _reconcile_conn(flavor, {"prof-gone": None})

    create.reconcile_flavor_profiles(conn, flavor, desired)

    conn.network.disassociate_flavor_from_service_profile.assert_not_called()
