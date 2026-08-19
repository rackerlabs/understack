"""Tests for ensure_profile drift detection in create.py."""

from __future__ import annotations

import logging
import types
from typing import Any
from unittest import mock

import pytest

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
) -> Any:
    raw_meta = dict(meta_info or {})
    if managed:
        raw_meta.update(common.OPERATOR_META_INFO_MARKERS)
    return types.SimpleNamespace(
        id=profile_id,
        driver=driver,
        meta_info=plugin_common.meta_info_payload(raw_meta),
    )


def _conn_with_profile(profile: Any) -> Any:
    network = mock.MagicMock()
    network.get_service_profile.return_value = profile
    return types.SimpleNamespace(network=network)


def _conn_without_profiles() -> Any:
    network = mock.MagicMock()
    network.get_service_profile.return_value = None
    network.service_profiles.return_value = []
    network.create_service_profile.return_value = _make_profile("new-profile")
    return types.SimpleNamespace(network=network)


# ---------------------------------------------------------------------------
# _profile_drifted
# ---------------------------------------------------------------------------


def test_no_drift_when_driver_and_meta_info_match():
    profile = _make_profile("p1", driver="some.Driver", meta_info={"vni_alloc": "auto"})
    assert create._profile_drifted(profile, "some.Driver", {"vni_alloc": "auto"}) == []


def test_drift_detected_on_driver_change():
    profile = _make_profile("p1", driver="old.Driver")
    drift = create._profile_drifted(profile, "new.Driver", {})
    assert len(drift) == 1
    assert "driver" in drift[0]
    assert "old.Driver" in drift[0]
    assert "new.Driver" in drift[0]


def test_drift_detected_on_meta_info_change():
    profile = _make_profile("p1", meta_info={"vni_alloc": "auto"})
    drift = create._profile_drifted(profile, profile.driver, {"vni_alloc": "on"})
    assert len(drift) == 1
    assert "meta_info" in drift[0]


def test_drift_detected_on_both_fields():
    profile = _make_profile("p1", driver="old.Driver", meta_info={"vni_alloc": "auto"})
    drift = create._profile_drifted(profile, "new.Driver", {"vni_alloc": "on"})
    assert len(drift) == 2


def test_drift_ignores_operator_marker_keys():
    """Operator-injected marker keys must not appear as drift.

    The profile in Neutron has OPERATOR_META_INFO_MARKERS merged in at creation
    time.  The CR spec only carries user-supplied keys.  The comparison must
    strip marker keys before diffing so a freshly created profile does not
    immediately report drift against its own CR.
    """
    desired_meta = {"vni_alloc": "auto"}
    profile = _make_profile("p1", meta_info=desired_meta, managed=True)
    # The profile's stored meta_info includes marker keys; desired_meta does not.
    drift = create._profile_drifted(profile, profile.driver, desired_meta)
    assert drift == []


# ---------------------------------------------------------------------------
# ensure_profile: configured_profile_id path drift warning
# ---------------------------------------------------------------------------


def test_ensure_profile_logs_warning_on_driver_drift(caplog):
    """A pinned profile whose driver diverged from the CR emits a WARNING."""
    profile = _make_profile("pinned-id", driver="old.Driver")
    conn = _conn_with_profile(profile)

    with caplog.at_level(
        logging.WARNING,
        logger="openstack_sync.plugins.neutron.router_flavors.create",
    ):
        result = create.ensure_profile(
            conn,
            name="test-flavor",
            driver="new.Driver",
            description="desc",
            meta_info={},
            configured_profile_id="pinned-id",
        )

    assert result is profile
    output = caplog.text
    assert "driver" in output
    assert "old.Driver" in output
    assert "new.Driver" in output


def test_ensure_profile_logs_warning_on_meta_info_drift(caplog):
    """A pinned profile whose meta_info diverged from the CR emits a WARNING."""
    profile = _make_profile("pinned-id", meta_info={"vni_alloc": "auto"})
    conn = _conn_with_profile(profile)

    with caplog.at_level(
        logging.WARNING,
        logger="openstack_sync.plugins.neutron.router_flavors.create",
    ):
        result = create.ensure_profile(
            conn,
            name="test-flavor",
            driver=profile.driver,
            description="desc",
            meta_info={"vni_alloc": "on"},
            configured_profile_id="pinned-id",
        )

    assert result is profile
    assert "meta_info" in caplog.text


def test_ensure_profile_no_warning_when_pinned_profile_matches(caplog):
    """A pinned profile that matches the spec emits no WARNING."""
    desired_meta = {"vni_alloc": "auto"}
    profile = _make_profile("pinned-id", meta_info=desired_meta, managed=True)
    conn = _conn_with_profile(profile)

    with caplog.at_level(
        logging.WARNING,
        logger="openstack_sync.plugins.neutron.router_flavors.create",
    ):
        create.ensure_profile(
            conn,
            name="test-flavor",
            driver=profile.driver,
            description="desc",
            meta_info=desired_meta,
            configured_profile_id="pinned-id",
        )

    assert not caplog.records


def test_ensure_profile_returns_profile_despite_drift():
    """Even when drift is detected the profile is still returned.

    We cannot fix the drift (Neutron rejects updates on in-use profiles), but
    we must not break the reconcile. The flavor should still get bound to the
    existing profile so the operator can continue to function.
    """
    profile = _make_profile("pinned-id", driver="old.Driver")
    conn = _conn_with_profile(profile)

    result = create.ensure_profile(
        conn,
        name="test-flavor",
        driver="new.Driver",
        description="desc",
        meta_info={},
        configured_profile_id="pinned-id",
    )

    assert result is profile


def test_ensure_profile_raises_when_configured_profile_id_is_missing():
    conn = _conn_without_profiles()

    with pytest.raises(plugin_common.ConfigError, match="missing-profile"):
        create.ensure_profile(
            conn,
            name="test-flavor",
            driver="some.Driver",
            description="desc",
            meta_info={},
            configured_profile_id="missing-profile",
        )

    conn.network.service_profiles.assert_not_called()
    conn.network.create_service_profile.assert_not_called()


def test_ensure_profile_creates_service_profile_with_management_markers():
    conn = _conn_without_profiles()

    create.ensure_profile(
        conn,
        name="test-flavor",
        driver="some.Driver",
        description="desc",
        meta_info={"vni_alloc": "auto"},
        configured_profile_id="",
    )

    kwargs = conn.network.create_service_profile.call_args.kwargs
    meta_info = plugin_common.normalize_meta_info(kwargs["meta_info"])
    assert meta_info["vni_alloc"] == "auto"
    for key, value in common.OPERATOR_META_INFO_MARKERS.items():
        assert meta_info[key] == value
