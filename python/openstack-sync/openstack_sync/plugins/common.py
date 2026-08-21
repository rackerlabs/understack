"""Generic utilities shared across all openstack-sync plugins.

Provides environment helpers, OpenStack SDK resource accessors,
meta_info normalisation, exception classifiers, and common API helpers
that are reusable by any plugin regardless of which OpenStack service it
targets.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from openstack import exceptions as openstack_exceptions

LOG = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def env_bool(name: str, default: bool) -> bool:
    """Return a boolean from an environment variable.

    Accepts only the exact values ``true`` and ``false``. Returns *default*
    when the variable is unset.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    if value == "true":
        return True
    if value == "false":
        return False
    raise ConfigError(f"{name} must be true or false")


def env_int(name: str, default: int) -> int:
    """Return an integer from an environment variable."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def env_float(name: str, default: float) -> float:
    """Return a float from an environment variable."""
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def env_required(name: str) -> str:
    """Return the value of a required environment variable.

    Raises :exc:`ConfigError` when the variable is absent or empty.  Use
    this for values that must be present at runtime but must not be read at
    import time (e.g. CRD identity vars injected by the Helm chart).
    """
    value = os.environ.get(name)
    if not value:
        raise ConfigError(
            f"{name} is required but not set; "
            "ensure the Helm chart has injected it before the hook runs"
        )
    return value


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when a plugin receives an invalid or incomplete configuration."""


# ---------------------------------------------------------------------------
# OpenStack SDK resource accessors
# ---------------------------------------------------------------------------


def get_value(resource: Any, name: str, default: Any = None) -> Any:
    """Return a field from a CR spec dict or an openstacksdk resource.

    Specs are plain dicts read by exact key; OpenStack resources are read by
    their openstacksdk attribute name (``meta_info``, ``service_profile_ids``),
    which the SDK has already mapped from the Neutron wire name.
    """
    value = (
        resource.get(name)
        if isinstance(resource, dict)
        else getattr(resource, name, None)
    )
    return default if value is None else value


def resource_id(resource: Any) -> str:
    """Return the string ID of an OpenStack resource."""
    return str(get_value(resource, "id"))


# ---------------------------------------------------------------------------
# meta_info helpers
# ---------------------------------------------------------------------------


def normalize_meta_info(value: Any) -> Any:
    """Normalise a meta_info value into a Python dict (or passthrough).

    The operator uses the openstacksdk field name ``meta_info``.  Neutron
    stores that value as JSON text, so existing service profiles may return a
    string while desired specs provide a dict.  Non-JSON strings pass through
    unchanged so drift reports can show the raw value.
    """
    if value is None or value == "":
        return {}

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    return value


def meta_info_payload(value: Any) -> str:
    """Return a canonical compact JSON string representation of *value*."""
    normalized = normalize_meta_info(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Neutron network readiness probe
# ---------------------------------------------------------------------------


def wait_for_openstack_network(
    conn: Any,
    retries: int = 30,
    delay: float = 10.0,
) -> None:
    """Poll until the Neutron network API is reachable.

    Args:
        conn: An authenticated OpenStack connection.
        retries: Maximum number of attempts before raising.
        delay: Seconds to wait between attempts.

    Raises:
        RuntimeError: When the API does not become ready within *retries*.
    """
    for attempt in range(1, retries + 1):
        try:
            next(iter(conn.network.flavors()), None)
            return
        except Exception as exc:
            if attempt >= retries:
                raise RuntimeError(
                    f"Neutron API did not become ready after {retries} attempt(s)"
                ) from exc
            LOG.info("Waiting for Neutron API (%s/%s): %s", attempt, retries, exc)
            time.sleep(delay)


# ---------------------------------------------------------------------------
# Service profile helpers
# ---------------------------------------------------------------------------


def get_service_profile(conn: Any, profile_id: str) -> Any | None:
    """Fetch a service profile by ID, returning None if it no longer exists."""
    try:
        return conn.network.get_service_profile(profile_id)
    except openstack_exceptions.NotFoundException:
        return None


def service_profile_ids(flavor: Any) -> list[str]:
    """Return the service profile IDs attached to *flavor*.

    The openstacksdk ``Flavor.service_profile_ids`` attribute maps Neutron's
    ``service_profiles`` wire field.
    """
    return [
        str(profile) for profile in get_value(flavor, "service_profile_ids", default=[])
    ]
