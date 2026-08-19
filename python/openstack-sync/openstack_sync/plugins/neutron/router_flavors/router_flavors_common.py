"""Router-flavor-specific constants and helpers.

Generic utilities (env helpers, resource accessors, meta_info, exception
classifiers, etc.) live in :mod:`openstack_sync.plugins.common`.
"""

from __future__ import annotations

import os
from typing import Any

from openstack_sync.plugins.common import comparable_meta_info_without
from openstack_sync.plugins.common import env_bool
from openstack_sync.plugins.common import env_tuple
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import managed_meta_info as managed_meta_info_with
from openstack_sync.plugins.common import meta_info_matches_without
from openstack_sync.plugins.common import normalize_meta_info
from openstack_sync.plugins.common import wait_for_openstack_network as wait_for_network

# ---------------------------------------------------------------------------
# Router-flavor CRD identity
# ---------------------------------------------------------------------------
# The chart injects these from the rendered CRD when the hook has an envPrefix.
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
DEFAULT_SERVICE_TYPE = "L3_ROUTER_NAT"

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
# Retry config
# ---------------------------------------------------------------------------

READY_RETRIES = int(os.environ.get("NEUTRON_ROUTER_FLAVOR_READY_RETRIES", "30"))
READY_DELAY = float(os.environ.get("NEUTRON_ROUTER_FLAVOR_READY_DELAY", "10"))


# ---------------------------------------------------------------------------
# meta_info helpers bound to this plugin's operator marker keys
# ---------------------------------------------------------------------------


def comparable_meta_info(value: Any) -> Any:
    """Strip operator marker keys from *value* before comparison."""
    return comparable_meta_info_without(value, OPERATOR_META_INFO_KEYS)


def meta_info_matches(current: Any, desired: Any) -> bool:
    """Return True when *current* and *desired* are logically equal.

    Operator-managed marker keys are ignored during comparison.
    """
    return meta_info_matches_without(current, desired, OPERATOR_META_INFO_KEYS)


def managed_meta_info(value: Any) -> Any:
    """Merge operator ownership markers into *value*."""
    return managed_meta_info_with(value, OPERATOR_META_INFO_MARKERS)


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
    return flavor_description_has_marker(get_value(flavor, "description", default=""))


# ---------------------------------------------------------------------------
# Service profile ownership helpers
# ---------------------------------------------------------------------------


def service_profile_meta_info(profile: Any) -> Any:
    """Return the meta_info field of *profile*."""
    return get_value(profile, "meta_info", default={})


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
    """Return the canonical meta_info payload from a router flavor spec."""
    return flavor_config.get("meta_info", {})


# ---------------------------------------------------------------------------
# Neutron readiness probe
# ---------------------------------------------------------------------------


def wait_for_openstack_network(conn: Any) -> None:
    """Poll until the Neutron network API is reachable.

    Uses ``READY_RETRIES`` and ``READY_DELAY`` from this module's env config.
    """
    wait_for_network(conn, retries=READY_RETRIES, delay=READY_DELAY)
