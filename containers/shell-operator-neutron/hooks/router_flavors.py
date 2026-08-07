#!/usr/bin/env python3
"""Reconcile Neutron router flavors and service profiles from JSON config."""

from __future__ import annotations

import ast
import json
import os
import sys
import time
from typing import Any


HOOK_CONFIG = {
    "configVersion": "v1",
    "onStartup": 1,
    "settings": {
        "executionMinInterval": "30s",
        "executionBurst": 1,
    },
}

CONFIG_PATH = os.environ.get(
    "NEUTRON_ROUTER_FLAVORS_CONFIG",
    "/etc/neutron-router-flavors/router_flavors.json",
)
DEFAULT_SERVICE_TYPE = os.environ.get(
    "NEUTRON_ROUTER_FLAVOR_SERVICE_TYPE",
    "L3_ROUTER_NAT",
)
READY_RETRIES = int(os.environ.get("NEUTRON_ROUTER_FLAVOR_READY_RETRIES", "30"))
READY_DELAY = float(os.environ.get("NEUTRON_ROUTER_FLAVOR_READY_DELAY", "10"))
_MISSING = object()


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


def meta_info_matches(current: Any, desired: Any) -> bool:
    return meta_info_payload(current) == meta_info_payload(desired)


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


def find_matching_profile(conn: Any, driver: str, meta_info: Any) -> Any | None:
    for profile in conn.network.service_profiles():
        if get_value(profile, "driver", "Driver", default="") != driver:
            continue

        if meta_info_matches(
            get_value(profile, "meta_info", default={}),
            meta_info,
        ):
            return profile

    return None


def ensure_profile(
    conn: Any,
    name: str,
    driver: str,
    description: str,
    meta_info: Any,
    configured_profile_id: str,
) -> Any:
    if configured_profile_id:
        profile = get_service_profile(conn, configured_profile_id)
        if profile:
            log(f"Using configured service profile {configured_profile_id} for {name}")
            return profile

        log(
            f"Configured service profile {configured_profile_id} "
            f"for {name} was not found"
        )

    profile = find_matching_profile(conn, driver, meta_info)
    if profile:
        profile_id = resource_id(profile)
        log(f"Reusing service profile {profile_id} for {name}")
        # Neutron rejects service profile updates once they are used by service instances.
        # Matching driver/meta_info is enough for idempotent reuse.
        return profile

    log(f"Creating service profile for {name} driver={driver}")
    return conn.network.create_service_profile(
        description=description,
        driver=driver,
        meta_info=meta_info_payload(meta_info),
        is_enabled=True,
    )


def find_flavor(conn: Any, name: str) -> Any | None:
    for flavor in conn.network.flavors(name=name):
        if get_value(flavor, "name", "Name") == name:
            return flavor

    return None


def ensure_flavor(conn: Any, name: str, service_type: str, description: str) -> Any:
    flavor = find_flavor(conn, name)
    if flavor:
        log(f"Router flavor {name} already exists")
        current_description = get_value(flavor, "description", "Description")
        if description and current_description != description:
            return conn.network.update_flavor(flavor, description=description)
        return flavor

    log(f"Creating router flavor {name} service_type={service_type}")
    attrs = {
        "name": name,
        "service_type": service_type,
        "is_enabled": True,
    }
    if description:
        attrs["description"] = description
    return conn.network.create_flavor(**attrs)


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


def ensure_profile_attached(conn: Any, flavor: Any, profile: Any) -> Any:
    flavor = conn.network.get_flavor(flavor)
    flavor_id = resource_id(flavor)
    profile_id = resource_id(profile)

    if profile_id in service_profile_ids(flavor):
        flavor_name = get_value(flavor, "name", "Name", default=flavor_id)
        log(f"Router flavor {flavor_name} already has service profile {profile_id}")
        return flavor

    log(f"Binding service profile {profile_id} to router flavor {flavor_id}")
    try:
        conn.network.associate_flavor_with_service_profile(flavor, profile)
    except Exception as exc:
        if not is_conflict(exc):
            raise
        log(f"Router flavor {flavor_id} already has service profile {profile_id}")

    return conn.network.get_flavor(flavor)


def render_flavor(flavor: Any) -> dict[str, Any]:
    return {
        "id": get_value(flavor, "id", "ID"),
        "name": get_value(flavor, "name", "Name"),
        "service_type": get_value(flavor, "service_type", "Service Type"),
        "description": get_value(flavor, "description", "Description"),
        "service_profile_ids": service_profile_ids(flavor),
    }


def config_meta_info(flavor_config: dict[str, Any]) -> Any:
    if "metainfo" in flavor_config:
        name = flavor_config.get("name", "<unknown>")
        raise ConfigError(f"Router flavor {name} uses metainfo; use meta_info instead")

    return flavor_config.get("meta_info", {})


def sync_flavor(conn: Any, flavor_config: dict[str, Any]) -> None:
    name = flavor_config.get("name")
    driver = flavor_config.get("driver")
    if not name or not driver:
        raise ConfigError(
            "Each router flavor entry must define name and driver: " f"{flavor_config}"
        )

    description = flavor_config.get("description", "")
    profile_description = flavor_config.get("profile_description", description)
    service_type = flavor_config.get("service_type", DEFAULT_SERVICE_TYPE)
    profile_id = flavor_config.get("profile_id", "")
    meta_info = config_meta_info(flavor_config)

    log(f"Reconciling router flavor {name}")
    profile = ensure_profile(
        conn,
        name,
        driver,
        profile_description,
        meta_info,
        profile_id,
    )
    flavor = ensure_flavor(conn, name, service_type, description)
    flavor = ensure_profile_attached(conn, flavor, profile)
    print(json.dumps(render_flavor(flavor), sort_keys=True))


def run() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(HOOK_CONFIG, indent=2))
        return 0

    flavors = load_config(CONFIG_PATH)
    conn = connect_openstack(os.environ.get("OS_CLOUD"))
    wait_for_openstack_network(conn)

    log(f"Found {len(flavors)} router flavor(s) to reconcile")
    for flavor_config in flavors:
        sync_flavor(conn, flavor_config)

    log("Finished reconciling router flavors")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:
        log(str(exc))
        sys.exit(1)
