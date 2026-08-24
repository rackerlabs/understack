"""Ownership markers for operator-managed router flavors and service profiles.

A NeutronRouterFlavor CR is an ownership claim for the matching OpenStack flavor
and service profiles. Resources the operator creates or adopts carry one of
these markers; prune only deletes resources that have already entered that
managed set.

Two mechanisms, because Neutron gives the two resources different places to
write to: service profiles carry marker keys inside ``meta_info``, flavors carry
a marker string appended to ``description``.
"""

from __future__ import annotations

from typing import Any

from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import meta_info_payload
from openstack_sync.plugins.common import normalize_meta_info

MANAGED_META_INFO_KEY = "_understack_router_flavor_operator"
MANAGED_META_INFO_VALUE = "managed"
MARKER_VERSION_META_INFO_KEY = "_understack_router_flavor_marker_version"
MARKER_VERSION_META_INFO_VALUE = "v1"
MARKER_SOURCE_META_INFO_KEY = "_understack_router_flavor_source"
MARKER_SOURCE_META_INFO_VALUE = "NeutronRouterFlavor"

FLAVOR_DESCRIPTION_MARKER = "[understack-router-flavor-operator]"

#: Marker keys stamped into a managed service profile's ``meta_info``.
OPERATOR_META_INFO_MARKERS = {
    MANAGED_META_INFO_KEY: MANAGED_META_INFO_VALUE,
    MARKER_VERSION_META_INFO_KEY: MARKER_VERSION_META_INFO_VALUE,
    MARKER_SOURCE_META_INFO_KEY: MARKER_SOURCE_META_INFO_VALUE,
}

_MARKER_KEYS = frozenset(OPERATOR_META_INFO_MARKERS)


# ---------------------------------------------------------------------------
# Service profiles: markers live in meta_info
# ---------------------------------------------------------------------------


def service_profile_meta_info(profile: Any) -> Any:
    """Return the ``meta_info`` of *profile*."""
    return get_value(profile, "meta_info", default={})


def _comparable(value: Any) -> Any:
    """Strip operator marker keys so specs and Neutron state compare equal."""
    normalized = normalize_meta_info(value)
    if isinstance(normalized, dict):
        return {k: v for k, v in normalized.items() if k not in _MARKER_KEYS}
    return normalized


def meta_info_matches(current: Any, desired: Any) -> bool:
    """Return True when *current* and *desired* meta_info are logically equal."""
    return meta_info_payload(_comparable(current)) == meta_info_payload(
        _comparable(desired)
    )


def managed_meta_info(value: Any) -> Any:
    """Return *value* with the operator ownership markers merged in."""
    normalized = normalize_meta_info(value)
    if not isinstance(normalized, dict):
        return normalized
    return {**normalized, **OPERATOR_META_INFO_MARKERS}


def is_managed_service_profile(profile: Any) -> bool:
    """Return True when *profile* carries the operator ownership marker."""
    meta_info = normalize_meta_info(service_profile_meta_info(profile))
    return (
        isinstance(meta_info, dict)
        and meta_info.get(MANAGED_META_INFO_KEY) == MANAGED_META_INFO_VALUE
    )


# ---------------------------------------------------------------------------
# Flavors: the marker lives in description
# ---------------------------------------------------------------------------


def clean_flavor_description(value: Any) -> str:
    """Return *value* with the operator description marker stripped."""
    return str(value or "").replace(FLAVOR_DESCRIPTION_MARKER, "").strip()


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
    """Return True when the flavor's description carries the operator marker."""
    return flavor_description_has_marker(get_value(flavor, "description", default=""))
