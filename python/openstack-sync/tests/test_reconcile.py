"""Tests for router flavor reconciliation.

Covers the profile cache, create-or-adopt by ``(driver, meta_info)``, profile
ownership transfer, drift reporting on reused profiles, the flavor
``service_type`` guard and ``is_enabled``/description reconcile, and the
flavor-to-profile binding set.
"""

from __future__ import annotations

import logging
import types
from typing import Any
from unittest import mock

import pytest
from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins import common as plugin_common
from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.neutron.router_flavors import markers
from openstack_sync.plugins.neutron.router_flavors import reconcile
from openstack_sync.plugins.neutron.router_flavors.config import SERVICE_TYPE

_DRIVER = "neutron_understack.l3_router.vrf.Vrf"
_NAME = "test-flavor"
_DESCRIPTION = "my flavor"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_profile(
    profile_id: str,
    driver: str = _DRIVER,
    meta_info: Any = None,
    managed: bool = True,
    is_enabled: bool = True,
    description: str = "desc",
) -> Any:
    """Build an openstacksdk-shaped service profile.

    ``description`` defaults to the ``_profile_spec`` default so a profile and a
    spec built with defaults are drift-free; drift tests pass a mismatch.
    """
    raw_meta = dict(meta_info or {})
    if managed:
        raw_meta.update(markers.OPERATOR_META_INFO_MARKERS)
    return types.SimpleNamespace(
        id=profile_id,
        driver=driver,
        is_enabled=is_enabled,
        description=description,
        meta_info=plugin_common.meta_info_payload(raw_meta),
    )


def _profile_spec(
    driver: str = _DRIVER,
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


def _make_flavor(
    flavor_id: str = "flavor-id",
    name: str = _NAME,
    service_profile_ids: list[str] | None = None,
    service_type: str = SERVICE_TYPE,
    description: str = f"{_DESCRIPTION} {markers.FLAVOR_DESCRIPTION_MARKER}",
    is_enabled: bool = True,
) -> Any:
    return types.SimpleNamespace(
        id=flavor_id,
        name=name,
        service_type=service_type,
        description=description,
        is_enabled=is_enabled,
        service_profile_ids=list(service_profile_ids or []),
    )


def _flavor_spec(
    name: str = _NAME,
    description: str = _DESCRIPTION,
    service_type: str = SERVICE_TYPE,
    is_enabled: bool = True,
    service_profiles: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a CR spec as the API server materialises it (defaults applied)."""
    return {
        "name": name,
        "description": description,
        "service_type": service_type,
        "is_enabled": is_enabled,
        "service_profiles": (
            service_profiles if service_profiles is not None else [_profile_spec()]
        ),
    }


def _reuse_conn(profile: Any) -> Any:
    """A connection whose only existing service profile is *profile*."""
    network = mock.MagicMock()
    network.service_profiles.return_value = [profile]
    return types.SimpleNamespace(network=network)


def _create_conn(created: Any, existing: list[Any] | None = None) -> Any:
    network = mock.MagicMock()
    network.service_profiles.return_value = list(existing or [])
    network.create_service_profile.return_value = created
    return types.SimpleNamespace(network=network)


def _bindings_conn(flavor: Any, lookup: dict[str, Any] | None = None) -> Any:
    """A connection for binding tests.

    ``get_flavor`` returns *flavor*; ``get_service_profile`` resolves unbind
    candidates from *lookup* so ownership can be evaluated.
    """
    resolved = lookup or {}
    network = mock.MagicMock()
    network.get_flavor.return_value = flavor
    network.get_service_profile.side_effect = lambda pid: resolved.get(pid)
    return types.SimpleNamespace(network=network)


# ---------------------------------------------------------------------------
# Profile cache
# ---------------------------------------------------------------------------


def test_profiles_for_driver_queries_by_driver():
    network = mock.MagicMock()
    network.service_profiles.return_value = [_make_profile("profile-id")]
    conn = types.SimpleNamespace(network=network)

    result = reconcile.profiles_for_driver(conn, "some.Driver", {})

    assert result == list(network.service_profiles.return_value)
    network.service_profiles.assert_called_once_with(driver="some.Driver")


def test_profiles_for_driver_caches_per_driver():
    first = _make_profile("first-profile", driver="first.Driver")
    second = _make_profile("second-profile", driver="second.Driver")
    network = mock.MagicMock()
    network.service_profiles.side_effect = [[first], [second]]
    conn = types.SimpleNamespace(network=network)
    cache: reconcile.ProfileCache = {}

    first_result = reconcile.profiles_for_driver(conn, "first.Driver", cache)
    cached = reconcile.profiles_for_driver(conn, "first.Driver", cache)
    second_result = reconcile.profiles_for_driver(conn, "second.Driver", cache)

    assert first_result == [first]
    assert cached is first_result
    assert second_result == [second]
    assert network.service_profiles.call_args_list == [
        mock.call(driver="first.Driver"),
        mock.call(driver="second.Driver"),
    ]


# ---------------------------------------------------------------------------
# ensure_profile: create or reuse by (driver, meta_info)
# ---------------------------------------------------------------------------


def test_ensure_profile_creates_with_ownership_markers():
    conn = _create_conn(_make_profile("new-profile"))

    reconcile.ensure_profile(
        conn, _NAME, _profile_spec(meta_info={"vni_alloc": "auto"}), {}, []
    )

    kwargs = conn.network.create_service_profile.call_args.kwargs
    assert kwargs["driver"] == _DRIVER
    assert kwargs["is_enabled"] is True
    meta_info = plugin_common.normalize_meta_info(kwargs["meta_info"])
    assert meta_info["vni_alloc"] == "auto"
    for key, value in markers.OPERATOR_META_INFO_MARKERS.items():
        assert meta_info[key] == value


def test_ensure_profile_creates_disabled_when_spec_disables():
    conn = _create_conn(_make_profile("new-profile", is_enabled=False))

    reconcile.ensure_profile(conn, _NAME, _profile_spec(is_enabled=False), {}, [])

    assert conn.network.create_service_profile.call_args.kwargs["is_enabled"] is False


def test_ensure_profile_reuses_existing_owned_profile():
    meta_info = {"vni_alloc": "auto"}
    existing = _make_profile("existing-profile", meta_info=meta_info)
    conn = _reuse_conn(existing)

    result = reconcile.ensure_profile(
        conn, _NAME, _profile_spec(meta_info=meta_info), {}, []
    )

    assert result is existing
    conn.network.create_service_profile.assert_not_called()


def test_ensure_profile_appends_created_profile_to_driver_cache():
    """A profile created for one flavor must be visible to the next flavor.

    The cache is shared across all flavors in a credential group, so two
    flavors with an identical ``(driver, meta_info)`` spec share one profile
    rather than each creating a duplicate.
    """
    meta_info = {"vni_alloc": "auto"}
    created = _make_profile("new-profile", meta_info=meta_info)
    conn = _create_conn(created)
    cache: reconcile.ProfileCache = {}

    first = reconcile.ensure_profile(
        conn, "flavor-a", _profile_spec(meta_info=meta_info), cache, []
    )
    second = reconcile.ensure_profile(
        conn, "flavor-b", _profile_spec(meta_info=meta_info), cache, []
    )

    assert first is created
    assert second is first
    conn.network.create_service_profile.assert_called_once()
    conn.network.service_profiles.assert_called_once_with(driver=_DRIVER)


def test_ensure_profile_does_not_reuse_across_drivers():
    meta_info = {"vni_alloc": "auto"}
    first_profile = _make_profile("first-profile", driver="first.Driver")
    second_profile = _make_profile("second-profile", driver="second.Driver")
    network = mock.MagicMock()
    network.service_profiles.side_effect = [[], []]
    network.create_service_profile.side_effect = [first_profile, second_profile]
    conn = types.SimpleNamespace(network=network)
    cache: reconcile.ProfileCache = {}

    first = reconcile.ensure_profile(
        conn,
        "flavor-a",
        _profile_spec(driver="first.Driver", meta_info=meta_info),
        cache,
        [],
    )
    second = reconcile.ensure_profile(
        conn,
        "flavor-b",
        _profile_spec(driver="second.Driver", meta_info=meta_info),
        cache,
        [],
    )

    assert first is first_profile
    assert second is second_profile
    assert network.create_service_profile.call_count == 2


# ---------------------------------------------------------------------------
# Matching profiles are adopted into operator ownership
# ---------------------------------------------------------------------------


def test_find_matching_profile_returns_unowned_match():
    meta_info = {"vni_alloc": "auto"}
    unowned = _make_profile("adhoc-profile", meta_info=meta_info, managed=False)

    assert reconcile.find_matching_profile([unowned], meta_info) is unowned


def test_find_matching_profile_prefers_owned_over_unowned():
    meta_info = {"vni_alloc": "auto"}
    unowned = _make_profile("adhoc-profile", meta_info=meta_info, managed=False)
    owned = _make_profile("owned-profile", meta_info=meta_info)

    assert reconcile.find_matching_profile([unowned, owned], meta_info) is owned


def test_ensure_profile_adopts_unowned_match():
    """A CR is an ownership claim for a matching existing profile."""
    meta_info = {"vni_alloc": "auto"}
    unowned = _make_profile("adhoc-profile", meta_info=meta_info, managed=False)
    adopted = _make_profile("adhoc-profile", meta_info=meta_info, managed=True)
    conn = _create_conn(_make_profile("new-profile"), existing=[unowned])
    conn.network.update_service_profile.return_value = adopted

    result = reconcile.ensure_profile(
        conn, _NAME, _profile_spec(meta_info=meta_info), {}, []
    )

    assert result is adopted
    conn.network.create_service_profile.assert_not_called()
    conn.network.update_service_profile.assert_called_once()
    new_meta = plugin_common.normalize_meta_info(
        conn.network.update_service_profile.call_args.kwargs["meta_info"]
    )
    for key, value in markers.OPERATOR_META_INFO_MARKERS.items():
        assert new_meta[key] == value


def test_ensure_profile_reports_bound_unowned_match_as_failure():
    """A profile that cannot be marked must not be used as managed state."""
    meta_info = {"vni_alloc": "auto"}
    unowned = _make_profile("adhoc-profile", meta_info=meta_info, managed=False)
    conn = _create_conn(_make_profile("new-profile"), existing=[unowned])
    conn.network.update_service_profile.side_effect = (
        openstack_exceptions.ConflictException
    )

    with pytest.raises(ConfigError, match="not operator-owned"):
        reconcile.ensure_profile(
            conn, _NAME, _profile_spec(meta_info=meta_info), {}, []
        )

    conn.network.create_service_profile.assert_not_called()
    conn.network.delete_service_profile.assert_not_called()


def test_ensure_profile_reuses_owned_when_unowned_match_also_exists():
    meta_info = {"vni_alloc": "auto"}
    unowned = _make_profile("adhoc-profile", meta_info=meta_info, managed=False)
    owned = _make_profile("owned-profile", meta_info=meta_info)
    network = mock.MagicMock()
    network.service_profiles.return_value = [unowned, owned]
    conn = types.SimpleNamespace(network=network)

    result = reconcile.ensure_profile(
        conn, _NAME, _profile_spec(meta_info=meta_info), {}, []
    )

    assert result is owned
    network.create_service_profile.assert_not_called()


def test_adopted_unowned_match_can_later_be_unbound():
    """Once adopted, a matching existing profile participates in normal cleanup."""
    meta_info = {"vni_alloc": "auto"}
    unowned = _make_profile("adhoc-profile", meta_info=meta_info, managed=False)
    adopted = _make_profile("adhoc-profile", meta_info=meta_info, managed=True)
    conn = _create_conn(_make_profile("new-profile"), existing=[unowned])
    conn.network.update_service_profile.return_value = adopted

    bound = reconcile.ensure_profile(
        conn, _NAME, _profile_spec(meta_info=meta_info), {}, []
    )

    flavor = _make_flavor(service_profile_ids=["adhoc-profile"])
    bindings = _bindings_conn(flavor, {"adhoc-profile": bound})

    reconcile.reconcile_flavor_profiles(bindings, flavor, [_make_profile("prof-b")])

    disassociate = bindings.network.disassociate_flavor_from_service_profile
    disassociate.assert_called_once()
    assert disassociate.call_args.args[1] is bound


# ---------------------------------------------------------------------------
# Drift reporting on reused profiles
# ---------------------------------------------------------------------------


def test_ensure_profile_reports_is_enabled_drift_on_reuse(caplog):
    """A profile disabled out-of-band is reported, not silently accepted.

    Neutron's get_flavor_next_provider raises ServiceProfileDisabled for the
    profile it selects, so every router create against the flavor fails while
    the flavor itself still looks converged.
    """
    existing = _make_profile("owned-profile", is_enabled=False)
    conn = _reuse_conn(existing)
    drift: list[reconcile.ProfileDrift] = []

    with caplog.at_level(logging.WARNING):
        result = reconcile.ensure_profile(
            conn, _NAME, _profile_spec(is_enabled=True), {}, drift
        )

    assert result is existing
    assert [(d.field, d.have, d.want) for d in drift] == [("is_enabled", False, True)]
    assert drift[0].profile_id == "owned-profile"
    assert "is_enabled" in caplog.text
    # Neutron rejects updates to a profile bound to any flavor: never try one.
    conn.network.update_service_profile.assert_not_called()


def test_ensure_profile_reports_description_drift_on_reuse():
    existing = _make_profile("owned-profile", description="stale")
    conn = _reuse_conn(existing)
    drift: list[reconcile.ProfileDrift] = []

    reconcile.ensure_profile(
        conn, _NAME, _profile_spec(description="wanted"), {}, drift
    )

    assert [(d.field, d.have, d.want) for d in drift] == [
        ("description", "stale", "wanted")
    ]


def test_ensure_profile_reports_every_drifted_field():
    existing = _make_profile("owned-profile", is_enabled=False, description="stale")
    conn = _reuse_conn(existing)
    drift: list[reconcile.ProfileDrift] = []

    reconcile.ensure_profile(
        conn, _NAME, _profile_spec(description="wanted", is_enabled=True), {}, drift
    )

    assert sorted(d.field for d in drift) == ["description", "is_enabled"]


def test_ensure_profile_accumulates_drift_across_profiles():
    """sync_flavor passes one list across every profile in the spec."""
    existing = _make_profile("owned-profile", is_enabled=False)
    conn = _reuse_conn(existing)
    already = reconcile.ProfileDrift(
        profile_id="other", field="is_enabled", have=False, want=True
    )
    drift = [already]

    reconcile.ensure_profile(conn, _NAME, _profile_spec(is_enabled=True), {}, drift)

    assert len(drift) == 2
    assert drift[0] is already


def test_ensure_profile_reports_no_drift_when_profile_matches_spec():
    conn = _reuse_conn(_make_profile("owned-profile"))
    drift: list[reconcile.ProfileDrift] = []

    reconcile.ensure_profile(conn, _NAME, _profile_spec(), {}, drift)

    assert drift == []


def test_ensure_profile_reports_no_drift_for_freshly_created_profile():
    """A profile the operator just created from the spec cannot have drifted."""
    conn = _create_conn(_make_profile("new-profile", is_enabled=False))
    drift: list[reconcile.ProfileDrift] = []

    reconcile.ensure_profile(conn, _NAME, _profile_spec(is_enabled=False), {}, drift)

    assert drift == []


def test_profile_drift_describe_names_profile_and_field():
    drift = reconcile.ProfileDrift(
        profile_id="prof-a", field="is_enabled", have=False, want=True
    )

    described = drift.describe()

    assert "prof-a" in described
    assert "is_enabled" in described
    assert "False" in described and "True" in described


# ---------------------------------------------------------------------------
# ensure_flavor: service_type is immutable
# ---------------------------------------------------------------------------


def test_ensure_flavor_raises_on_service_type_mismatch():
    flavor = _make_flavor(service_type="DIFFERENT_TYPE")
    conn = mock.MagicMock()
    conn.network.flavors.return_value = [flavor]

    with pytest.raises(ConfigError, match="service_type"):
        reconcile.ensure_flavor(conn, _flavor_spec())


def test_ensure_flavor_error_message_contains_both_service_types():
    flavor = _make_flavor(service_type="WRONG")
    conn = mock.MagicMock()
    conn.network.flavors.return_value = [flavor]

    with pytest.raises(ConfigError) as exc_info:
        reconcile.ensure_flavor(conn, _flavor_spec())

    message = str(exc_info.value)
    assert "WRONG" in message
    assert SERVICE_TYPE in message
    assert _NAME in message


# ---------------------------------------------------------------------------
# ensure_flavor: is_enabled and description reconcile
# ---------------------------------------------------------------------------


def _existing_flavor_conn(flavor: Any, updated: Any | None = None) -> Any:
    conn = mock.MagicMock()
    conn.network.flavors.return_value = [flavor]
    conn.network.update_flavor.return_value = updated or _make_flavor()
    return conn


def test_ensure_flavor_reenables_disabled_flavor(caplog):
    conn = _existing_flavor_conn(_make_flavor(is_enabled=False))

    with caplog.at_level(logging.INFO, logger="openstack_sync"):
        reconcile.ensure_flavor(conn, _flavor_spec(is_enabled=True))

    conn.network.update_flavor.assert_called_once()
    assert conn.network.update_flavor.call_args.kwargs["is_enabled"] is True
    assert "is_enabled drift" in caplog.text
    assert "have=False" in caplog.text
    assert "want=True" in caplog.text


def test_ensure_flavor_disables_when_spec_disables(caplog):
    conn = _existing_flavor_conn(_make_flavor(is_enabled=True))

    with caplog.at_level(logging.INFO, logger="openstack_sync"):
        reconcile.ensure_flavor(conn, _flavor_spec(is_enabled=False))

    conn.network.update_flavor.assert_called_once()
    assert conn.network.update_flavor.call_args.kwargs["is_enabled"] is False
    assert "have=True" in caplog.text
    assert "want=False" in caplog.text


def test_ensure_flavor_no_update_when_both_disabled():
    flavor = _make_flavor(is_enabled=False)
    conn = _existing_flavor_conn(flavor)

    result = reconcile.ensure_flavor(conn, _flavor_spec(is_enabled=False))

    conn.network.update_flavor.assert_not_called()
    assert result is flavor


def test_ensure_flavor_no_update_when_already_correct():
    flavor = _make_flavor(is_enabled=True)
    conn = _existing_flavor_conn(flavor)

    result = reconcile.ensure_flavor(conn, _flavor_spec(is_enabled=True))

    conn.network.update_flavor.assert_not_called()
    assert result is flavor


def test_ensure_flavor_reenables_even_when_description_matches():
    """is_enabled drift must trigger an update even if the description is current."""
    conn = _existing_flavor_conn(_make_flavor(is_enabled=False))

    reconcile.ensure_flavor(conn, _flavor_spec(is_enabled=True))

    conn.network.update_flavor.assert_called_once()


def test_ensure_flavor_updates_changed_description():
    conn = _existing_flavor_conn(_make_flavor(description="old description"))

    reconcile.ensure_flavor(conn, _flavor_spec())

    conn.network.update_flavor.assert_called_once()


def test_ensure_flavor_adds_missing_marker():
    conn = _existing_flavor_conn(_make_flavor(description="no marker here"))

    reconcile.ensure_flavor(conn, _flavor_spec())

    conn.network.update_flavor.assert_called_once()
    kwargs = conn.network.update_flavor.call_args.kwargs
    assert markers.FLAVOR_DESCRIPTION_MARKER in kwargs["description"]


# ---------------------------------------------------------------------------
# ensure_flavor: creates when absent
# ---------------------------------------------------------------------------


def test_ensure_flavor_creates_when_not_found():
    conn = mock.MagicMock()
    conn.network.flavors.return_value = []
    conn.network.create_flavor.return_value = _make_flavor()

    reconcile.ensure_flavor(conn, _flavor_spec())

    kwargs = conn.network.create_flavor.call_args.kwargs
    assert kwargs["name"] == _NAME
    assert kwargs["service_type"] == SERVICE_TYPE
    assert kwargs["is_enabled"] is True
    assert markers.FLAVOR_DESCRIPTION_MARKER in kwargs["description"]


def test_ensure_flavor_creates_disabled_from_spec():
    """A CR that opts out of enabled must create the Neutron flavor disabled."""
    conn = mock.MagicMock()
    conn.network.flavors.return_value = []
    conn.network.create_flavor.return_value = _make_flavor(is_enabled=False)

    reconcile.ensure_flavor(conn, _flavor_spec(is_enabled=False))

    assert conn.network.create_flavor.call_args.kwargs["is_enabled"] is False


def test_find_flavor_ignores_partial_name_match():
    """Guards against a future change to substring query semantics."""
    conn = mock.MagicMock()
    conn.network.flavors.return_value = [_make_flavor(name="test-flavor-other")]

    assert reconcile.find_flavor(conn, _NAME) is None


# ---------------------------------------------------------------------------
# reconcile_flavor_profiles: bind missing, unbind owned extras
# ---------------------------------------------------------------------------


def test_reconcile_flavor_profiles_no_op_when_matching():
    flavor = _make_flavor(service_profile_ids=["prof-a", "prof-b"])
    conn = _bindings_conn(flavor)

    result = reconcile.reconcile_flavor_profiles(
        conn, flavor, [_make_profile("prof-a"), _make_profile("prof-b")]
    )

    conn.network.associate_flavor_with_service_profile.assert_not_called()
    conn.network.disassociate_flavor_from_service_profile.assert_not_called()
    assert result is flavor


def test_reconcile_flavor_profiles_binds_missing():
    flavor = _make_flavor(service_profile_ids=[])
    conn = _bindings_conn(flavor)

    reconcile.reconcile_flavor_profiles(
        conn, flavor, [_make_profile("prof-a"), _make_profile("prof-b")]
    )

    calls = conn.network.associate_flavor_with_service_profile.call_args_list
    assert sorted(call.args[1].id for call in calls) == ["prof-a", "prof-b"]
    conn.network.disassociate_flavor_from_service_profile.assert_not_called()


def test_reconcile_flavor_profiles_unbinds_owned_extra():
    flavor = _make_flavor(service_profile_ids=["prof-a", "prof-extra"])
    extra = _make_profile("prof-extra")
    conn = _bindings_conn(flavor, {"prof-extra": extra})

    reconcile.reconcile_flavor_profiles(conn, flavor, [_make_profile("prof-a")])

    conn.network.associate_flavor_with_service_profile.assert_not_called()
    conn.network.disassociate_flavor_from_service_profile.assert_called_once()
    assert (
        conn.network.disassociate_flavor_from_service_profile.call_args.args[1] is extra
    )


def test_reconcile_flavor_profiles_keeps_unowned_extra():
    """A profile attached out-of-band must not be unbound."""
    flavor = _make_flavor(service_profile_ids=["prof-a", "prof-adhoc"])
    unowned = _make_profile("prof-adhoc", managed=False)
    conn = _bindings_conn(flavor, {"prof-adhoc": unowned})

    reconcile.reconcile_flavor_profiles(conn, flavor, [_make_profile("prof-a")])

    conn.network.disassociate_flavor_from_service_profile.assert_not_called()


def test_reconcile_flavor_profiles_binds_and_unbinds_together():
    flavor = _make_flavor(service_profile_ids=["prof-old"])
    old = _make_profile("prof-old")
    conn = _bindings_conn(flavor, {"prof-old": old})

    reconcile.reconcile_flavor_profiles(conn, flavor, [_make_profile("prof-new")])

    conn.network.associate_flavor_with_service_profile.assert_called_once()
    assert (
        conn.network.associate_flavor_with_service_profile.call_args.args[1].id
        == "prof-new"
    )
    conn.network.disassociate_flavor_from_service_profile.assert_called_once()
    assert (
        conn.network.disassociate_flavor_from_service_profile.call_args.args[1] is old
    )


def test_reconcile_flavor_profiles_skips_deleted_extra():
    """An unbind candidate that no longer exists is a silent no-op."""
    flavor = _make_flavor(service_profile_ids=["prof-a", "prof-gone"])
    conn = _bindings_conn(flavor, {"prof-gone": None})

    reconcile.reconcile_flavor_profiles(conn, flavor, [_make_profile("prof-a")])

    conn.network.disassociate_flavor_from_service_profile.assert_not_called()


# ---------------------------------------------------------------------------
# sync_flavor
# ---------------------------------------------------------------------------


def _sync_conn(flavor: Any, existing_profiles: list[Any] | None = None) -> Any:
    conn = mock.MagicMock()
    conn.network.flavors.return_value = [flavor]
    conn.network.get_flavor.return_value = flavor
    conn.network.service_profiles.return_value = list(existing_profiles or [])
    conn.network.create_service_profile.return_value = _make_profile("prof-a")
    return conn


def test_sync_flavor_returns_no_notes_when_nothing_drifted():
    flavor = _make_flavor(service_profile_ids=["prof-a"])
    conn = _sync_conn(flavor)

    assert reconcile.sync_flavor(conn, _flavor_spec(), {}) == []


def test_sync_flavor_reports_profile_drift():
    """Drift found while resolving profiles reaches the caller as notes.

    The flavor itself is converged, so this is not a failure -- but the caller
    must be able to qualify the status it reports.
    """
    flavor = _make_flavor(service_profile_ids=["owned-profile"])
    drifted_profile = _make_profile("owned-profile", is_enabled=False)
    conn = _sync_conn(flavor, existing_profiles=[drifted_profile])

    notes = reconcile.sync_flavor(
        conn, _flavor_spec(service_profiles=[_profile_spec(is_enabled=True)]), {}
    )

    assert len(notes) == 1
    assert "owned-profile" in notes[0]
    assert "is_enabled" in notes[0]


def test_sync_flavor_passes_is_enabled_from_spec():
    """The value the API server put on the CR reaches the Neutron flavor."""
    flavor = _make_flavor(is_enabled=True, service_profile_ids=["prof-a"])
    conn = _sync_conn(flavor)
    conn.network.update_flavor.return_value = flavor

    reconcile.sync_flavor(conn, _flavor_spec(is_enabled=False), {})

    conn.network.update_flavor.assert_called_once()
    assert conn.network.update_flavor.call_args.kwargs["is_enabled"] is False
