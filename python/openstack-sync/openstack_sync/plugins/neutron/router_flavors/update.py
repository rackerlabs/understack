"""Update and sync logic for configured Neutron router flavors."""

from __future__ import annotations

import json
from typing import Any

from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import service_profile_ids
from openstack_sync.plugins.neutron.router_flavors import create
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    DEFAULT_SERVICE_TYPE,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    ConfigError,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    clean_flavor_description,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    config_meta_info,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    flavor_description_has_marker,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import log
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    managed_flavor_description,
)


def ensure_flavor(conn: Any, name: str, service_type: str, description: str) -> Any:
    flavor = create.find_flavor(conn, name)
    managed_description = managed_flavor_description(description)
    if flavor:
        log(f"Router flavor {name} already exists")
        current_description = get_value(
            flavor, "description", "Description", default=""
        )
        description_changed = clean_flavor_description(
            current_description
        ) != clean_flavor_description(description)
        marker_missing = not flavor_description_has_marker(current_description)
        if description_changed or marker_missing:
            return conn.network.update_flavor(flavor, description=managed_description)
        return flavor

    return create.create_flavor(conn, name, service_type, description)


def render_flavor(flavor: Any) -> dict[str, Any]:
    return {
        "id": get_value(flavor, "id", "ID"),
        "name": get_value(flavor, "name", "Name"),
        "service_type": get_value(flavor, "service_type", "Service Type"),
        "description": get_value(flavor, "description", "Description"),
        "service_profile_ids": service_profile_ids(flavor),
    }


def sync_flavor(conn: Any, flavor_config: dict[str, Any]) -> None:
    name = flavor_config.get("name")
    driver = flavor_config.get("driver")
    if not name or not driver:
        raise ConfigError(
            f"Each router flavor entry must define name and driver: {flavor_config}"
        )

    description = flavor_config.get("description", "")
    profile_description = flavor_config.get("profile_description", description)
    service_type = flavor_config.get("service_type", DEFAULT_SERVICE_TYPE)
    profile_id = flavor_config.get("profile_id", "")
    meta_info = config_meta_info(flavor_config)

    log(f"Reconciling router flavor {name}")
    profile = create.ensure_profile(
        conn, name, driver, profile_description, meta_info, profile_id
    )
    flavor = ensure_flavor(conn, name, service_type, description)
    flavor = create.ensure_profile_attached(conn, flavor, profile)
    log(
        f"Reconciled router flavor: {json.dumps(render_flavor(flavor), sort_keys=True)}"
    )
