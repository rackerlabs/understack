"""Update and sync logic for configured Neutron router flavors."""

from __future__ import annotations

import json
from typing import Any

from . import create_router_flavors
from . import router_flavors_common as common


def ensure_flavor(conn: Any, name: str, service_type: str, description: str) -> Any:
    flavor = create_router_flavors.find_flavor(conn, name)
    managed_description = common.managed_flavor_description(description)
    if flavor:
        common.log(f"Router flavor {name} already exists")
        current_description = common.get_value(
            flavor,
            "description",
            "Description",
            default="",
        )
        description_changed = common.clean_flavor_description(
            current_description
        ) != common.clean_flavor_description(description)
        marker_missing = not common.flavor_description_has_marker(current_description)
        if description_changed or marker_missing:
            return conn.network.update_flavor(flavor, description=managed_description)
        return flavor

    return create_router_flavors.create_flavor(conn, name, service_type, description)


def render_flavor(flavor: Any) -> dict[str, Any]:
    return {
        "id": common.get_value(flavor, "id", "ID"),
        "name": common.get_value(flavor, "name", "Name"),
        "service_type": common.get_value(flavor, "service_type", "Service Type"),
        "description": common.get_value(flavor, "description", "Description"),
        "service_profile_ids": common.service_profile_ids(flavor),
    }


def sync_flavor(conn: Any, flavor_config: dict[str, Any]) -> None:
    name = flavor_config.get("name")
    driver = flavor_config.get("driver")
    if not name or not driver:
        raise common.ConfigError(
            "Each router flavor entry must define name and driver: " f"{flavor_config}"
        )

    description = flavor_config.get("description", "")
    profile_description = flavor_config.get("profile_description", description)
    service_type = flavor_config.get("service_type", common.DEFAULT_SERVICE_TYPE)
    profile_id = flavor_config.get("profile_id", "")
    meta_info = common.config_meta_info(flavor_config)

    common.log(f"Reconciling router flavor {name}")
    profile = create_router_flavors.ensure_profile(
        conn,
        name,
        driver,
        profile_description,
        meta_info,
        profile_id,
    )
    flavor = ensure_flavor(conn, name, service_type, description)
    flavor = create_router_flavors.ensure_profile_attached(conn, flavor, profile)
    print(json.dumps(render_flavor(flavor), sort_keys=True))
