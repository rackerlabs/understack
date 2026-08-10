"""Shared helpers for Neutron router flavor reconciliation."""

from __future__ import annotations

import ast
import json
import os
import sys
import time
from typing import Any


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_tuple(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        item.strip()
        for item in os.environ.get(name, default).split(",")
        if item.strip()
    )


SYNC_CRONTAB = os.environ.get("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *")
CONFIG_PATH = os.environ.get(
    "NEUTRON_ROUTER_FLAVORS_CONFIG",
    "/etc/neutron-router-flavors/router_flavors.json",
)
DEFAULT_SERVICE_TYPE = os.environ.get(
    "NEUTRON_ROUTER_FLAVOR_SERVICE_TYPE",
    "L3_ROUTER_NAT",
)
PRUNE_REMOVED_FLAVORS = env_bool("NEUTRON_ROUTER_FLAVOR_PRUNE", False)
DELETE_UNUSED_SERVICE_PROFILES = env_bool(
    "NEUTRON_ROUTER_FLAVOR_DELETE_UNUSED_PROFILES",
    True,
)
PRUNE_DRIVER_PREFIXES = env_tuple(
    "NEUTRON_ROUTER_FLAVOR_PRUNE_DRIVER_PREFIXES",
    "neutron_understack.l3_router.",
)
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
MARKER_SOURCE_META_INFO_VALUE = os.path.basename(CONFIG_PATH) or "router_flavors.json"
OPERATOR_META_INFO_MARKERS = {
    MANAGED_META_INFO_KEY: MANAGED_META_INFO_VALUE,
    MARKER_VERSION_META_INFO_KEY: MARKER_VERSION_META_INFO_VALUE,
    MARKER_SOURCE_META_INFO_KEY: MARKER_SOURCE_META_INFO_VALUE,
}
OPERATOR_META_INFO_KEYS = frozenset(OPERATOR_META_INFO_MARKERS)
READY_RETRIES = int(os.environ.get("NEUTRON_ROUTER_FLAVOR_READY_RETRIES", "30"))
READY_DELAY = float(os.environ.get("NEUTRON_ROUTER_FLAVOR_READY_DELAY", "10"))
_MISSING = object()

# Markers used by this hook:
# - flavor.description contains [understack-router-flavor-operator]: ownership
#   marker for router flavors. This lets the hook distinguish config-managed
#   flavors from manually created flavors, including flavors that use an
#   externally configured profile_id.
# - service_profile.meta_info["_understack_router_flavor_operator"]="managed":
#   ownership marker for service profiles. Destructive profile cleanup requires
#   this exact marker so manual service profiles are not deleted.
# - service_profile.meta_info["_understack_router_flavor_marker_version"]="v1":
#   marker schema version for future migrations.
# - service_profile.meta_info["_understack_router_flavor_source"]=<config file>:
#   traceability marker showing where the service profile was sourced from.
#
# Router flavors do not expose service-profile-style meta_info in the API used
# here, so the flavor marker is stored in description. Keep it compact because
# users may see the description in OpenStack output.


class ConfigError(Exception):
    pass


def log(message: str) -> None:
    print(f"[router_flavors] {message}", file=sys.stderr)


def _resource_value(resource: Any, name: str) -> Any:
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
    for name in names:
        value = _resource_value(resource, name)
        if value is not _MISSING and value is not None:
            return value

    return default


def resource_id(resource: Any) -> str:
    value = get_value(resource, "id", "ID", "Id")
    if not value:
        raise RuntimeError(f"Unable to read ID from resource {resource!r}")
    return str(value)


def normalize_meta_info(value: Any) -> Any:
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
    normalized = normalize_meta_info(value)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def comparable_meta_info(value: Any) -> Any:
    normalized = normalize_meta_info(value)
    if isinstance(normalized, dict):
        return {
            key: item
            for key, item in normalized.items()
            if key not in OPERATOR_META_INFO_KEYS
        }
    return normalized


def meta_info_matches(current: Any, desired: Any) -> bool:
    return meta_info_payload(comparable_meta_info(current)) == meta_info_payload(
        comparable_meta_info(desired)
    )


def managed_meta_info(value: Any) -> Any:
    normalized = normalize_meta_info(value)
    if not isinstance(normalized, dict):
        return normalized

    managed = dict(normalized)
    managed.update(OPERATOR_META_INFO_MARKERS)
    return managed


def clean_flavor_description(value: Any) -> str:
    description = "" if value is None else str(value)
    return description.replace(FLAVOR_DESCRIPTION_MARKER, "").strip()


def managed_flavor_description(value: Any) -> str:
    description = clean_flavor_description(value)
    if not description:
        return FLAVOR_DESCRIPTION_MARKER
    return f"{description} {FLAVOR_DESCRIPTION_MARKER}"


def flavor_description_has_marker(value: Any) -> bool:
    return FLAVOR_DESCRIPTION_MARKER in str(value or "")


def is_managed_flavor(flavor: Any) -> bool:
    return flavor_description_has_marker(
        get_value(flavor, "description", "Description", default="")
    )


def service_profile_meta_info(profile: Any) -> Any:
    return get_value(profile, "meta_info", "metainfo", default={})


def is_managed_service_profile(profile: Any) -> bool:
    meta_info = normalize_meta_info(service_profile_meta_info(profile))
    return (
        isinstance(meta_info, dict)
        and meta_info.get(MANAGED_META_INFO_KEY) == MANAGED_META_INFO_VALUE
    )


def is_not_found(exc: Exception) -> bool:
    return getattr(exc, "status_code", None) == 404 or exc.__class__.__name__ in {
        "NotFoundException",
        "ResourceNotFound",
    }


def is_conflict(exc: Exception) -> bool:
    return (
        getattr(exc, "status_code", None) == 409
        or exc.__class__.__name__ in {"ConflictException", "ResourceConflict"}
        or "already" in str(exc).lower()
    )


def connect_openstack(os_cloud: str | None) -> Any:
    try:
        import openstack
    except ImportError as exc:
        raise RuntimeError("openstacksdk is required to run this hook") from exc

    return openstack.connect(cloud=os_cloud)


def load_config(path: str) -> list[dict[str, Any]]:
    if not os.path.isfile(path):
        raise ConfigError(f"Router flavor config not found at {path}")

    with open(path, encoding="utf-8") as config_file:
        flavors = json.load(config_file)

    if not isinstance(flavors, list):
        raise ConfigError("Router flavor config must be a JSON list")

    return flavors


def wait_for_openstack_network(conn: Any) -> None:
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


def get_service_profile(conn: Any, profile_id: str) -> Any | None:
    try:
        return conn.network.get_service_profile(profile_id)
    except Exception as exc:
        if is_not_found(exc):
            return None
        raise


def service_profile_ids(flavor: Any) -> list[str]:
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


def config_meta_info(flavor_config: dict[str, Any]) -> Any:
    if "metainfo" in flavor_config:
        name = flavor_config.get("name", "<unknown>")
        raise ConfigError(f"Router flavor {name} uses metainfo; use meta_info instead")

    return flavor_config.get("meta_info", {})
