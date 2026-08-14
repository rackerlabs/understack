"""Router-flavor-specific constants and helpers.

Generic utilities (env helpers, resource accessors, meta_info, exception
classifiers, etc.) live in :mod:`openstack_sync.plugins.common`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openstack_sync.plugins.common import comparable_meta_info_without
from openstack_sync.plugins.common import env_bool
from openstack_sync.plugins.common import env_float
from openstack_sync.plugins.common import env_int
from openstack_sync.plugins.common import env_required
from openstack_sync.plugins.common import env_tuple
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import managed_meta_info as managed_meta_info_with
from openstack_sync.plugins.common import meta_info_matches_without
from openstack_sync.plugins.common import normalize_meta_info
from openstack_sync.plugins.common import wait_for_openstack_network as wait_for_network

# ---------------------------------------------------------------------------
# Router-flavor CRD identity
# ---------------------------------------------------------------------------
# CRD_API_VERSION, CRD_KIND, and CRD_RESOURCE are injected by the Helm chart
# at runtime and must NOT be read at module import time.  Importing this module
# happens before shell-operator invokes the hook with --config, and these vars
# are not guaranteed to be present at that point (e.g. broken chart rendering,
# unit tests that only exercise the --config path).
#
# Use the accessor functions below — crd_api_version(), crd_kind(),
# crd_resource() — everywhere these values are needed.  They call
# env_required() which raises ConfigError with a clear message if a var is
# absent, rather than crashing at import with a raw KeyError.
#
# Internal shell-operator binding label default.
CRD_BINDING_NAME = "neutron-router-flavors"
DEFAULT_SERVICE_TYPE = "L3_ROUTER_NAT"


def crd_api_version() -> str:
    """Return the CRD API version injected by the Helm chart."""
    return env_required("NEUTRON_ROUTER_FLAVOR_CRD_API_VERSION")


def crd_kind() -> str:
    """Return the CRD kind injected by the Helm chart."""
    return env_required("NEUTRON_ROUTER_FLAVOR_CRD_KIND")


def crd_resource() -> str:
    """Return the fully-qualified CRD resource name injected by the Helm chart."""
    return env_required("NEUTRON_ROUTER_FLAVOR_CRD_RESOURCE")


def crd_binding_name() -> str:
    """Return the shell-operator binding label for the CRD watch."""
    return os.environ.get("NEUTRON_ROUTER_FLAVOR_CRD_BINDING_NAME", CRD_BINDING_NAME)


def crd_namespace() -> str | None:
    """Return the namespace used for CRD status patches."""
    return os.environ.get("POD_NAMESPACE")


def status_enabled() -> bool:
    """Return whether CRD status patching is enabled."""
    return env_bool("NEUTRON_ROUTER_FLAVOR_STATUS_ENABLED", False)


# ---------------------------------------------------------------------------
# Prune / lifecycle config
# ---------------------------------------------------------------------------


def prune_removed_flavors_enabled() -> bool:
    """Return whether removed router flavor pruning is enabled."""
    return env_bool("NEUTRON_ROUTER_FLAVOR_PRUNE", False)


def delete_unused_service_profiles_enabled() -> bool:
    """Return whether unused service profile deletion is enabled."""
    return env_bool("NEUTRON_ROUTER_FLAVOR_DELETE_UNUSED_PROFILES", True)


def prune_driver_prefixes() -> tuple[str, ...]:
    """Return service profile driver prefixes eligible for pruning."""
    return env_tuple(
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

# ---------------------------------------------------------------------------
# Retry config
# ---------------------------------------------------------------------------


def ready_retries() -> int:
    """Return the Neutron readiness retry count."""
    return env_int("NEUTRON_ROUTER_FLAVOR_READY_RETRIES", 30)


def ready_delay() -> float:
    """Return the Neutron readiness delay in seconds."""
    return env_float("NEUTRON_ROUTER_FLAVOR_READY_DELAY", 10)


# ---------------------------------------------------------------------------
# Runtime-resolved marker helpers
# ---------------------------------------------------------------------------
# MARKER_SOURCE defaults to the CRD kind, which is only available at runtime.
# Use marker_source() rather than a module-level constant.


def marker_source() -> str:
    """Return the marker source value, defaulting to the CRD kind."""
    return os.environ.get("NEUTRON_ROUTER_FLAVOR_SOURCE") or crd_kind()


def operator_meta_info_markers() -> dict[str, str]:
    """Return the operator ownership marker dict."""
    return {
        MANAGED_META_INFO_KEY: MANAGED_META_INFO_VALUE,
        MARKER_VERSION_META_INFO_KEY: MARKER_VERSION_META_INFO_VALUE,
        MARKER_SOURCE_META_INFO_KEY: marker_source(),
    }


def operator_meta_info_keys() -> frozenset[str]:
    """Return the frozenset of operator marker keys."""
    return frozenset(operator_meta_info_markers())


# ---------------------------------------------------------------------------
# meta_info helpers bound to this plugin's operator marker keys
# ---------------------------------------------------------------------------


def comparable_meta_info(value: Any) -> Any:
    """Strip operator marker keys from *value* before comparison."""
    return comparable_meta_info_without(value, operator_meta_info_keys())


def meta_info_matches(current: Any, desired: Any) -> bool:
    """Return True when *current* and *desired* are logically equal.

    Operator-managed marker keys are ignored during comparison.
    """
    return meta_info_matches_without(current, desired, operator_meta_info_keys())


def managed_meta_info(value: Any) -> Any:
    """Merge operator ownership markers into *value*."""
    return managed_meta_info_with(value, operator_meta_info_markers())


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
# Service profile drift reporting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfileDrift:
    """One field of a reused service profile that diverged from the CR spec.

    Profile drift is reported, never auto-corrected.  Neutron's
    ``update_service_profile`` calls ``_ensure_service_profile_not_in_use`` and
    raises ``ServiceProfileInUse`` (HTTP 409) while *any* flavor binding exists
    -- not merely while a router is using it -- and this operator binds every
    profile it manages.  An update attempt would therefore fail every cycle.
    Correcting drift requires unbinding the profile from every flavor first,
    which is an operator decision, not something to do behind their back.
    """

    profile_id: str
    driver: str
    field: str
    have: Any
    want: Any

    def describe(self) -> str:
        """Return a short ``field: have=... want=...`` description."""
        return f"{self.field}: have={self.have!r} want={self.want!r}"


def describe_profile_drift(drift: list[ProfileDrift]) -> str:
    """Return a single-line summary of *drift* for logs and CR status."""
    return "; ".join(
        f"service profile {item.profile_id} {item.describe()}" for item in drift
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

    Reads retry config at call time so malformed values do not break hook
    import or shell-operator --config registration.
    """
    wait_for_network(conn, retries=ready_retries(), delay=ready_delay())
