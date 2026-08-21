"""Tests for update.ensure_flavor and update.sync_flavor.

Covers the service_type guard, is_enabled drift reconcile (both directions),
create-with-is_enabled-from-spec, and the sync_flavor spec pass-through.
"""

from __future__ import annotations

import types
from typing import Any
from unittest import mock

import pytest

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.neutron.router_flavors import update
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    FLAVOR_DESCRIPTION_MARKER,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    ProfileDrift,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NAME = "test-flavor"
_SERVICE_TYPE = "L3_ROUTER_NAT"
_DESCRIPTION = "my flavor"


def _make_flavor(
    *,
    name: str = _NAME,
    service_type: str = _SERVICE_TYPE,
    description: str = f"{_DESCRIPTION} {FLAVOR_DESCRIPTION_MARKER}",
    is_enabled: bool = True,
) -> Any:
    return types.SimpleNamespace(
        name=name,
        service_type=service_type,
        description=description,
        is_enabled=is_enabled,
    )


# ---------------------------------------------------------------------------
# service_type mismatch — must raise ConfigError
# ---------------------------------------------------------------------------


def test_ensure_flavor_raises_on_service_type_mismatch():
    flavor = _make_flavor(service_type="DIFFERENT_TYPE")
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        with pytest.raises(ConfigError, match="service_type"):
            update.ensure_flavor(
                conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=True
            )


def test_ensure_flavor_error_message_contains_both_service_types():
    flavor = _make_flavor(service_type="WRONG")
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        with pytest.raises(ConfigError) as exc_info:
            update.ensure_flavor(
                conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=True
            )
    msg = str(exc_info.value)
    assert "WRONG" in msg
    assert _SERVICE_TYPE in msg
    assert _NAME in msg


# ---------------------------------------------------------------------------
# is_enabled reconcile
# ---------------------------------------------------------------------------


def test_ensure_flavor_reenables_disabled_flavor(caplog):
    """Neutron has is_enabled=False but spec says True → update to True."""
    flavor = _make_flavor(is_enabled=False)
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        conn.network.update_flavor.return_value = _make_flavor(is_enabled=True)
        with caplog.at_level("INFO", logger="openstack_sync"):
            update.ensure_flavor(
                conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=True
            )

    conn.network.update_flavor.assert_called_once()
    _, kwargs = conn.network.update_flavor.call_args
    assert kwargs["is_enabled"] is True
    assert "is_enabled drift" in caplog.text
    assert "have=False" in caplog.text
    assert "want=True" in caplog.text


def test_ensure_flavor_disables_enabled_flavor_when_spec_disables(caplog):
    """Neutron has is_enabled=True but spec says False → update to False."""
    flavor = _make_flavor(is_enabled=True)
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        conn.network.update_flavor.return_value = _make_flavor(is_enabled=False)
        with caplog.at_level("INFO", logger="openstack_sync"):
            update.ensure_flavor(
                conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=False
            )

    conn.network.update_flavor.assert_called_once()
    _, kwargs = conn.network.update_flavor.call_args
    assert kwargs["is_enabled"] is False
    assert "is_enabled drift" in caplog.text
    assert "have=True" in caplog.text
    assert "want=False" in caplog.text


def test_ensure_flavor_no_update_when_both_disabled():
    """Neutron has is_enabled=False and spec says False → no Neutron call."""
    flavor = _make_flavor(is_enabled=False)
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        result = update.ensure_flavor(
            conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=False
        )

    conn.network.update_flavor.assert_not_called()
    assert result is flavor


def test_ensure_flavor_reenables_disabled_flavor_even_when_description_matches():
    """is_enabled=False must trigger an update even if description is current."""
    flavor = _make_flavor(is_enabled=False)
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        conn.network.update_flavor.return_value = _make_flavor(is_enabled=True)
        update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=True)

    conn.network.update_flavor.assert_called_once()


def test_ensure_flavor_no_update_when_already_correct():
    """No Neutron call when description and is_enabled are already correct."""
    flavor = _make_flavor(is_enabled=True)
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        result = update.ensure_flavor(
            conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=True
        )

    conn.network.update_flavor.assert_not_called()
    assert result is flavor


# ---------------------------------------------------------------------------
# description drift still triggers update
# ---------------------------------------------------------------------------


def test_ensure_flavor_updates_changed_description():
    flavor = _make_flavor(description="old description")
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        conn.network.update_flavor.return_value = _make_flavor()
        update.ensure_flavor(
            conn, _NAME, _SERVICE_TYPE, "new description", is_enabled=True
        )

    conn.network.update_flavor.assert_called_once()


def test_ensure_flavor_adds_missing_marker():
    flavor = _make_flavor(description="no marker here")
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        conn.network.update_flavor.return_value = _make_flavor()
        update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=True)

    conn.network.update_flavor.assert_called_once()
    _, kwargs = conn.network.update_flavor.call_args
    assert FLAVOR_DESCRIPTION_MARKER in kwargs["description"]


# ---------------------------------------------------------------------------
# flavor not found — creates it
# ---------------------------------------------------------------------------


def test_ensure_flavor_creates_when_not_found():
    with (
        mock.patch(
            "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
            return_value=None,
        ),
        mock.patch(
            "openstack_sync.plugins.neutron.router_flavors.create.create_flavor",
            return_value=_make_flavor(),
        ) as mock_create,
    ):
        conn = mock.MagicMock()
        update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=True)

    mock_create.assert_called_once_with(
        conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=True
    )


def test_ensure_flavor_creates_with_is_enabled_from_spec():
    """A CR that opts out of enabled must create the Neutron flavor disabled."""
    with (
        mock.patch(
            "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
            return_value=None,
        ),
        mock.patch(
            "openstack_sync.plugins.neutron.router_flavors.create.create_flavor",
            return_value=_make_flavor(is_enabled=False),
        ) as mock_create,
    ):
        conn = mock.MagicMock()
        update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=False)

    mock_create.assert_called_once_with(
        conn, _NAME, _SERVICE_TYPE, _DESCRIPTION, is_enabled=False
    )


# ---------------------------------------------------------------------------
# sync_flavor: reads is_enabled from the CR spec
# ---------------------------------------------------------------------------


def _sync_flavor_config(*, is_enabled: bool) -> dict[str, Any]:
    """Build a CR-shaped flavor_config.

    ``is_enabled`` mirrors the CRD default (true) that the k8s API server
    materialises on admission; every real spec reaching the hook carries it.
    """
    return {
        "name": _NAME,
        "description": _DESCRIPTION,
        "service_type": _SERVICE_TYPE,
        "is_enabled": is_enabled,
        "service_profiles": [
            {
                "driver": "neutron_understack.l3_router.vrf.Vrf",
                "description": "profile description",
                "meta_info": {},
                "is_enabled": True,
            }
        ],
    }


def _sync_flavor_mocks(flavor: Any):
    """Yield the mock stack used by sync_flavor pass-through tests.

    Uses a real openstacksdk-shaped flavor (SimpleNamespace with
    ``service_profile_ids``) so ``render_flavor`` succeeds when
    ``sync_flavor`` logs the reconciled result.
    """
    rendered = types.SimpleNamespace(
        id="flavor-id",
        name=_NAME,
        service_type=_SERVICE_TYPE,
        description=flavor.description,
        is_enabled=flavor.is_enabled,
        service_profile_ids=["profile-id"],
    )
    return (
        mock.patch(
            "openstack_sync.plugins.neutron.router_flavors.update.ensure_flavor",
            return_value=rendered,
        ),
        mock.patch(
            "openstack_sync.plugins.neutron.router_flavors.create.ensure_profile"
        ),
        mock.patch(
            "openstack_sync.plugins.neutron.router_flavors.create."
            "reconcile_flavor_profiles",
            return_value=rendered,
        ),
    )


def test_sync_flavor_passes_is_enabled_true_from_spec():
    """The value the k8s API server put on the CR reaches ensure_flavor."""
    conn = mock.MagicMock()
    flavor = _make_flavor(is_enabled=True)
    ensure_patch, profile_patch, attached_patch = _sync_flavor_mocks(flavor)
    with ensure_patch as mock_ensure, profile_patch, attached_patch:
        update.sync_flavor(conn, _sync_flavor_config(is_enabled=True), {})

    assert mock_ensure.call_args.kwargs["is_enabled"] is True


def test_sync_flavor_passes_is_enabled_false_from_spec():
    conn = mock.MagicMock()
    flavor = _make_flavor(is_enabled=False)
    ensure_patch, profile_patch, attached_patch = _sync_flavor_mocks(flavor)
    with ensure_patch as mock_ensure, profile_patch, attached_patch:
        update.sync_flavor(conn, _sync_flavor_config(is_enabled=False), {})

    assert mock_ensure.call_args.kwargs["is_enabled"] is False


# ---------------------------------------------------------------------------
# sync_flavor: service profile drift reaches the caller
# ---------------------------------------------------------------------------


def test_sync_flavor_returns_empty_drift_when_nothing_drifted():
    conn = mock.MagicMock()
    flavor = _make_flavor(is_enabled=True)
    ensure_patch, profile_patch, attached_patch = _sync_flavor_mocks(flavor)
    with ensure_patch, profile_patch, attached_patch:
        result = update.sync_flavor(conn, _sync_flavor_config(is_enabled=True), {})

    assert result == []


def test_sync_flavor_propagates_profile_drift():
    """Drift collected while resolving profiles is returned to the caller.

    The flavor itself is converged, so this is not a reconcile failure -- but
    the caller must be able to qualify the status it reports.
    """
    conn = mock.MagicMock()
    flavor = _make_flavor(is_enabled=True)
    ensure_patch, profile_patch, attached_patch = _sync_flavor_mocks(flavor)
    drifted = ProfileDrift(
        profile_id="prof-a",
        driver="neutron_understack.l3_router.vrf.Vrf",
        field="is_enabled",
        have=False,
        want=True,
    )

    def ensure_profile(conn, name, profile_spec, profile_cache, drift=None):
        if drift is not None:
            drift.append(drifted)
        return types.SimpleNamespace(id="prof-a")

    with ensure_patch, profile_patch as mock_profile, attached_patch:
        mock_profile.side_effect = ensure_profile
        result = update.sync_flavor(conn, _sync_flavor_config(is_enabled=True), {})

    assert result == [drifted]
