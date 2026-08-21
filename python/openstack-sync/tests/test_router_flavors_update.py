"""Tests for update.ensure_flavor — service_type guard and is_enabled reconcile."""

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
            update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION)


def test_ensure_flavor_error_message_contains_both_service_types():
    flavor = _make_flavor(service_type="WRONG")
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        with pytest.raises(ConfigError) as exc_info:
            update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION)
    msg = str(exc_info.value)
    assert "WRONG" in msg
    assert _SERVICE_TYPE in msg
    assert _NAME in msg


# ---------------------------------------------------------------------------
# is_enabled reconcile
# ---------------------------------------------------------------------------


def test_ensure_flavor_reenables_disabled_flavor(caplog):
    flavor = _make_flavor(is_enabled=False)
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        conn.network.update_flavor.return_value = _make_flavor(is_enabled=True)
        with caplog.at_level("INFO", logger="openstack_sync"):
            update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION)

    conn.network.update_flavor.assert_called_once()
    _, kwargs = conn.network.update_flavor.call_args
    assert kwargs["is_enabled"] is True
    assert "re-enabling" in caplog.text


def test_ensure_flavor_reenables_disabled_flavor_even_when_description_matches():
    """is_enabled=False must trigger an update even if description is current."""
    flavor = _make_flavor(is_enabled=False)
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        conn.network.update_flavor.return_value = _make_flavor(is_enabled=True)
        update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION)

    conn.network.update_flavor.assert_called_once()


def test_ensure_flavor_no_update_when_already_correct():
    """No Neutron call when description and is_enabled are already correct."""
    flavor = _make_flavor(is_enabled=True)
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        result = update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION)

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
        update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, "new description")

    conn.network.update_flavor.assert_called_once()


def test_ensure_flavor_adds_missing_marker():
    flavor = _make_flavor(description="no marker here")
    with mock.patch(
        "openstack_sync.plugins.neutron.router_flavors.create.find_flavor",
        return_value=flavor,
    ):
        conn = mock.MagicMock()
        conn.network.update_flavor.return_value = _make_flavor()
        update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION)

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
        update.ensure_flavor(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION)

    mock_create.assert_called_once_with(conn, _NAME, _SERVICE_TYPE, _DESCRIPTION)
