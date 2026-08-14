"""Generic utilities shared across all openstack-sync plugins.

Provides environment helpers, duck-typed OpenStack resource accessors,
meta_info normalisation, exception classifiers, and common API helpers
that are reusable by any plugin regardless of which OpenStack service it
targets.
"""

from __future__ import annotations

import ast
import json
import os
import time
from typing import Any

from openstack_sync.utils import get_openstack_connection

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def env_bool(name: str, default: bool) -> bool:
    """Return a boolean from an environment variable.

    Accepts ``1 / true / yes / on`` (case-insensitive) as truthy values.
    Returns *default* when the variable is unset.
    """
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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
# Duck-typed OpenStack resource accessors
# ---------------------------------------------------------------------------

_MISSING = object()


def _resource_value(resource: Any, name: str) -> Any:
    """Read *name* from *resource* regardless of type.

    Handles dicts, SDK objects with ``.get()``, plain attributes, and objects
    with a ``.to_dict()`` method.  Returns the ``_MISSING`` sentinel when the
    name cannot be found.
    """
    if isinstance(resource, dict):
        return resource[name] if name in resource else _MISSING

    getter = getattr(resource, "get", None)
    if callable(getter):
        try:
            value = getter(name, _MISSING)
        except TypeError:
            try:
                value = getter(name)
            except Exception:
                value = _MISSING
        except Exception:
            value = _MISSING

        if value is not _MISSING:
            return value

    value = getattr(resource, name, _MISSING)
    if value is not _MISSING:
        return value

    try:
        data = resource.to_dict(computed=False)
    except Exception:
        data = {}

    return data[name] if name in data else _MISSING


def get_value(resource: Any, *names: str, default: Any = None) -> Any:
    """Return the first non-None value found under any of *names* in *resource*.

    Tries each name in turn using :func:`_resource_value`, supporting dicts,
    OpenStack SDK objects (which use inconsistent casing like ``id`` vs
    ``ID``), and objects with a ``.to_dict()`` method.
    """
    for name in names:
        value = _resource_value(resource, name)
        if value is not _MISSING and value is not None:
            return value
    return default


def resource_id(resource: Any) -> str:
    """Return the string ID of an OpenStack resource.

    Tries ``id``, ``ID``, and ``Id`` in that order.

    Raises:
        RuntimeError: When no ID field can be found.
    """
    value = get_value(resource, "id", "ID", "Id")
    if not value:
        raise RuntimeError(f"Unable to read ID from resource {resource!r}")
    return str(value)


# ---------------------------------------------------------------------------
# meta_info helpers
# ---------------------------------------------------------------------------


def normalize_meta_info(value: Any) -> Any:
    """Normalise a meta_info value into a Python dict (or passthrough).

    Neutron stores ``service_profile.meta_info`` as a JSON string in some SDK
    versions and as a dict in others.  This function handles both, as well as
    Python literal strings produced by older tooling.
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
            try:
                return ast.literal_eval(text)
            except (SyntaxError, ValueError):
                return text

    return value


def meta_info_payload(value: Any) -> str:
    """Return a canonical compact JSON string representation of *value*."""
    normalized = normalize_meta_info(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def comparable_meta_info(value: Any) -> Any:
    """Strip operator-managed keys from *value* before comparison.

    Operator marker keys (e.g. ``_understack_router_flavor_operator``) are
    injected at creation time and must not trigger spurious updates when
    comparing desired vs current state.  The caller is responsible for
    passing the set of keys to strip via the module-level constant in the
    plugin's ``common`` module.
    """
    normalized = normalize_meta_info(value)
    if isinstance(normalized, dict):
        return {k: v for k, v in normalized.items()}
    return normalized


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
    """Return True for 404 / ResourceNotFound exceptions."""
    return getattr(exc, "status_code", None) == 404 or exc.__class__.__name__ in {
        "NotFoundException",
        "ResourceNotFound",
    }


def is_conflict(exc: Exception) -> bool:
    """Return True for 409 / ConflictException / 'already exists' exceptions."""
    return (
        getattr(exc, "status_code", None) == 409
        or exc.__class__.__name__ in {"ConflictException", "ResourceConflict"}
        or "already" in str(exc).lower()
    )


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
    log_fn: Any = None,
) -> None:
    """Poll until the Neutron network API is reachable.

    Args:
        conn: An authenticated OpenStack connection.
        retries: Maximum number of attempts before raising.
        delay: Seconds to wait between attempts.
        log_fn: Optional callable used to emit progress messages.

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
            if log_fn:
                log_fn(f"Waiting for Neutron API ({attempt}/{retries}): {exc}")
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

    Handles the SDK's inconsistent field names (``service_profile_ids``,
    ``service_profiles``, ``profiles``) and CSV string representations.
    """
    profiles = get_value(
        flavor,
        "service_profile_ids",
        "service_profiles",
        "profiles",
        default=[],
    )
    if profiles is None:
        return []
    if isinstance(profiles, str):
        return [item.strip() for item in profiles.split(",") if item.strip()]
    return [str(profile) for profile in profiles]
