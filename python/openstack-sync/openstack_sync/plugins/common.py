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

from openstack_sync.utils import get_openstack_connection

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


def env_tuple(name: str, default: str) -> tuple[str, ...]:
    """Return a tuple of strings parsed from a comma-separated env variable."""
    return tuple(
        item.strip()
        for item in os.environ.get(name, default).split(",")
        if item.strip()
    )


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Raised when a plugin receives an invalid or incomplete configuration."""


# ---------------------------------------------------------------------------
# OpenStack SDK resource accessors
# ---------------------------------------------------------------------------

_MISSING = object()


def _mapping_value(mapping: dict[str, Any], name: str) -> Any:
    """Read *name* from a mapping without invoking default values."""
    try:
        return mapping[name]
    except KeyError:
        return _MISSING


def _attribute_value(resource: Any, name: str) -> Any:
    """Read *name* through attribute access."""
    try:
        return getattr(resource, name)
    except AttributeError:
        return _MISSING


def _resource_value(resource: Any, name: str) -> Any:
    """Read *name* from *resource* regardless of type.

    Plain dicts are the operator contract and are read by exact key.
    OpenStack resources are read through their openstacksdk attribute names,
    for example ``meta_info`` and ``service_profile_ids``.  Neutron wire names
    are mapped by openstacksdk before this layer reads them.
    """
    if type(resource) is dict:
        return _mapping_value(resource, name)

    value = _attribute_value(resource, name)
    if value is not _MISSING:
        return value

    return _MISSING


def get_value(resource: Any, name: str, default: Any = None) -> Any:
    """Return a non-None value from *resource* by canonical field name."""
    value = _resource_value(resource, name)
    if value is not _MISSING and value is not None:
        return value
    return default


def resource_id(resource: Any) -> str:
    """Return the string ID of an OpenStack resource.

    Raises:
        RuntimeError: When no ID field can be found.
    """
    value = get_value(resource, "id")
    if not value:
        raise RuntimeError(f"Unable to read ID from resource {resource!r}")
    return str(value)


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


def comparable_meta_info_without(value: Any, exclude_keys: frozenset[str]) -> Any:
    """Strip *exclude_keys* from *value* before comparison."""
    normalized = normalize_meta_info(value)
    if isinstance(normalized, dict):
        return {k: v for k, v in normalized.items() if k not in exclude_keys}
    return normalized


def meta_info_matches_without(
    current: Any, desired: Any, exclude_keys: frozenset[str]
) -> bool:
    """Return True when *current* and *desired* are logically equal.

    Keys in *exclude_keys* are stripped before comparison.
    """
    return meta_info_payload(
        comparable_meta_info_without(current, exclude_keys)
    ) == meta_info_payload(comparable_meta_info_without(desired, exclude_keys))


def managed_meta_info(value: Any, markers: dict[str, str]) -> Any:
    """Merge *markers* into *value*, returning the combined meta_info dict."""
    normalized = normalize_meta_info(value)
    if not isinstance(normalized, dict):
        return normalized
    managed = dict(normalized)
    managed.update(markers)
    return managed


# ---------------------------------------------------------------------------
# Exception classifiers
# ---------------------------------------------------------------------------


def is_not_found(exc: Exception) -> bool:
    """Return True for openstacksdk 404 exceptions."""
    return isinstance(exc, openstack_exceptions.NotFoundException)


def is_conflict(exc: Exception) -> bool:
    """Return True for openstacksdk 409 exceptions."""
    return isinstance(exc, openstack_exceptions.ConflictException)


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def validate_config(items: Any, source: str) -> list[dict[str, Any]]:
    """Validate that *items* is a list of dicts.

    Args:
        items: The value to validate.
        source: Human-readable label used in error messages.

    Returns:
        A shallow copy of the validated list.

    Raises:
        ConfigError: When *items* is not a list or contains a non-dict element.
    """
    if not isinstance(items, list):
        raise ConfigError(f"{source} must be a list")
    validated = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ConfigError(f"{source}[{index}] must be an object")
        validated.append(dict(item))
    return validated


# ---------------------------------------------------------------------------
# OpenStack connection
# ---------------------------------------------------------------------------


def connect_openstack(secret_name: str, cloud_name: str) -> Any:
    """Return an authenticated OpenStack connection loaded from a K8s Secret.

    Delegates to :func:`openstack_sync.utils.get_openstack_connection` so
    credentials are read from Kubernetes rather than a file on disk.
    """
    return get_openstack_connection(secret_name, cloud_name)


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
    """Fetch a service profile by ID, returning None if not found."""
    try:
        return conn.network.get_service_profile(profile_id)
    except Exception as exc:
        if is_not_found(exc):
            return None
        raise


def service_profile_ids(flavor: Any) -> list[str]:
    """Return the list of service profile IDs attached to *flavor*.

    The openstacksdk ``Flavor.service_profile_ids`` attribute maps Neutron's
    ``service_profiles`` wire field.
    """
    profiles = get_value(flavor, "service_profile_ids", default=[])
    if profiles is None:
        return []
    if not isinstance(profiles, list):
        raise TypeError("flavor.service_profile_ids must be a list")
    return [str(profile) for profile in profiles]
