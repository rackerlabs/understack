"""Router-flavor-specific constants and helpers.

Generic utilities (env helpers, resource accessors, meta_info, exception
classifiers, etc.) live in :mod:`openstack_sync.plugins.common`.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import env_bool
from openstack_sync.plugins.common import env_tuple
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import meta_info_payload
from openstack_sync.plugins.common import normalize_meta_info

# ---------------------------------------------------------------------------
# Router-flavor CRD identity
# ---------------------------------------------------------------------------
# These four are always injected by the Helm chart from the CRD file via
CRD_API_VERSION = os.environ["NEUTRON_ROUTER_FLAVOR_CRD_API_VERSION"]
CRD_KIND = os.environ["NEUTRON_ROUTER_FLAVOR_CRD_KIND"]
CRD_RESOURCE = os.environ["NEUTRON_ROUTER_FLAVOR_CRD_RESOURCE"]
STATUS_ENABLED = env_bool("NEUTRON_ROUTER_FLAVOR_STATUS_ENABLED", False)
# Internal shell-operator binding label -- not injected externally.
CRD_BINDING_NAME = os.environ.get(
    "NEUTRON_ROUTER_FLAVOR_CRD_BINDING_NAME",
    "neutron-router-flavors",
)
CRD_NAMESPACE = os.environ.get("POD_NAMESPACE")
DEFAULT_SERVICE_TYPE = os.environ.get(
    "NEUTRON_ROUTER_FLAVOR_SERVICE_TYPE",
    "L3_ROUTER_NAT",
)

# ---------------------------------------------------------------------------
# Prune / lifecycle config
# ---------------------------------------------------------------------------

PRUNE_REMOVED_FLAVORS = env_bool("NEUTRON_ROUTER_FLAVOR_PRUNE", False)
DELETE_UNUSED_SERVICE_PROFILES = env_bool(
    "NEUTRON_ROUTER_FLAVOR_DELETE_UNUSED_PROFILES",
    True,
)
PRUNE_DRIVER_PREFIXES = env_tuple(
    "NEUTRON_ROUTER_FLAVOR_PRUNE_DRIVER_PREFIXES",
    "neutron_understack.l3_router.",
)

# ---------------------------------------------------------------------------
# Operator ownership markers
# ---------------------------------------------------------------------------

MANAGED_META_INFO_KEY = os.environ.get(
    "NEUTRON_ROUTER_FLAVOR_MANAGED_META_INFO_KEY",
    "_understack_router_flavor_operator",
)
MANAGED_META_INFO_VALUE = "managed"
FLAVOR_DESCRIPTION_MARKER = os.environ.get(
    "NEUTRON_ROUTER_FLAVOR_DESCRIPTION_MARKER",
    "[understack-router-flavor-operator]",
)
MARKER_VERSION_META_INFO_KEY = "_understack_router_flavor_marker_version"
MARKER_VERSION_META_INFO_VALUE = "v1"
MARKER_SOURCE_META_INFO_KEY = "_understack_router_flavor_source"
MARKER_SOURCE_META_INFO_VALUE = os.environ.get(
    "NEUTRON_ROUTER_FLAVOR_SOURCE",
    CRD_KIND,
)
OPERATOR_META_INFO_MARKERS: dict[str, str] = {
    MANAGED_META_INFO_KEY: MANAGED_META_INFO_VALUE,
    MARKER_VERSION_META_INFO_KEY: MARKER_VERSION_META_INFO_VALUE,
    MARKER_SOURCE_META_INFO_KEY: MARKER_SOURCE_META_INFO_VALUE,
}
OPERATOR_META_INFO_KEYS = frozenset(OPERATOR_META_INFO_MARKERS)

# ---------------------------------------------------------------------------
# Retry / credential defaults
# ---------------------------------------------------------------------------

READY_RETRIES = int(os.environ.get("NEUTRON_ROUTER_FLAVOR_READY_RETRIES", "30"))
READY_DELAY = float(os.environ.get("NEUTRON_ROUTER_FLAVOR_READY_DELAY", "10"))

DEFAULT_SECRET = os.environ["NEUTRON_ROUTER_FLAVOR_DEFAULT_SECRET"]
DEFAULT_CLOUD = os.environ["NEUTRON_ROUTER_FLAVOR_DEFAULT_CLOUD"]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log(message: str) -> None:
    """Write a prefixed message to stderr."""
    print(f"[router_flavors] {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# meta_info — plugin-specific wrappers that close over OPERATOR_META_INFO_KEYS
# ---------------------------------------------------------------------------


def comparable_meta_info(value: Any) -> Any:
    """Strip operator marker keys from *value* before comparison."""
    normalized = normalize_meta_info(value)
    if isinstance(normalized, dict):
        return {k: v for k, v in normalized.items() if k not in OPERATOR_META_INFO_KEYS}
    return normalized


def meta_info_matches(current: Any, desired: Any) -> bool:
    """Return True when *current* and *desired* are logically equal.

    Operator-managed marker keys are ignored during comparison.
    """
    return meta_info_payload(comparable_meta_info(current)) == meta_info_payload(
        comparable_meta_info(desired)
    )


def managed_meta_info(value: Any) -> Any:
    """Merge operator ownership markers into *value*."""
    normalized = normalize_meta_info(value)
    if not isinstance(normalized, dict):
        return normalized
    merged = dict(normalized)
    merged.update(OPERATOR_META_INFO_MARKERS)
    return merged


# ---------------------------------------------------------------------------
# Flavor description marker helpers
# ---------------------------------------------------------------------------


def clean_flavor_description(value: Any) -> str:
    """Return *value* with the operator description marker stripped."""
    description = "" if value is None else str(value)
    return description.replace(FLAVOR_DESCRIPTION_MARKER, "").strip()


def managed_flavor_description(value: Any) -> str:
    """Return *value* with the operator description marker appended."""
    description = clean_flavor_description(value)
    if not description:
        return FLAVOR_DESCRIPTION_MARKER
    return f"{description} {FLAVOR_DESCRIPTION_MARKER}"


def flavor_description_has_marker(value: Any) -> bool:
    """Return True when *value* contains the operator description marker."""
    return FLAVOR_DESCRIPTION_MARKER in str(value or "")


def is_managed_flavor(flavor: Any) -> bool:
    """Return True when the flavor's description contains the operator marker."""
    return flavor_description_has_marker(
        get_value(flavor, "description", "Description", default="")
    )


# ---------------------------------------------------------------------------
# Service profile ownership helpers
# ---------------------------------------------------------------------------


def service_profile_meta_info(profile: Any) -> Any:
    """Return the meta_info field of *profile*."""
    return get_value(profile, "meta_info", "metainfo", default={})


def is_managed_service_profile(profile: Any) -> bool:
    """Return True when the service profile carries the operator ownership marker."""
    meta_info = normalize_meta_info(service_profile_meta_info(profile))
    return (
        isinstance(meta_info, dict)
        and meta_info.get(MANAGED_META_INFO_KEY) == MANAGED_META_INFO_VALUE
    )


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def config_meta_info(flavor_config: dict[str, Any]) -> Any:
    """Extract and validate meta_info from a flavor config dict.

    Raises:
        ConfigError: When the deprecated ``metainfo`` key is used instead of
            ``meta_info``.
    """
    if "metainfo" in flavor_config:
        name = flavor_config.get("name", "<unknown>")
        raise ConfigError(f"Router flavor {name} uses metainfo; use meta_info instead")
    return flavor_config.get("meta_info", {})


# ---------------------------------------------------------------------------
# Neutron readiness probe — thin wrapper that uses module-level retry config
# ---------------------------------------------------------------------------


def wait_for_openstack_network(conn: Any) -> None:
    """Poll until the Neutron network API is reachable.

    Uses ``READY_RETRIES`` and ``READY_DELAY`` from this module's env config.
    """
    for attempt in range(1, READY_RETRIES + 1):
        try:
            next(iter(conn.network.flavors()), None)
            return
        except Exception as exc:
            if attempt >= READY_RETRIES:
                raise RuntimeError(
                    f"Neutron API did not become ready after {READY_RETRIES} attempt(s)"
                ) from exc
            log(f"Waiting for Neutron API ({attempt}/{READY_RETRIES}): {exc}")
            time.sleep(READY_DELAY)
