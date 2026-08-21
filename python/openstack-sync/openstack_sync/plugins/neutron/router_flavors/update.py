"""Update and sync logic for configured Neutron router flavors."""

from __future__ import annotations

import json
import logging
from typing import Any

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import service_profile_ids
from openstack_sync.plugins.neutron.router_flavors import create
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    DEFAULT_SERVICE_TYPE,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    clean_flavor_description,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    flavor_description_has_marker,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    managed_flavor_description,
)

LOG = logging.getLogger(__name__)


def ensure_flavor(
    conn: Any,
    name: str,
    service_type: str,
    description: str,
    *,
    is_enabled: bool,
) -> Any:
    flavor = create.find_flavor(conn, name)
    managed_description = managed_flavor_description(description)
    if flavor:
        LOG.info("Router flavor %s already exists", name)

        current_service_type = get_value(flavor, "service_type", default="")
        if current_service_type != service_type:
            raise ConfigError(
                f"Router flavor {name!r} already exists in Neutron with "
                f"service_type={current_service_type!r}; "
                f"expected {service_type!r}. Neutron does not allow updating "
                f"service_type on an existing flavor. Rename the CR or remove "
                f"the existing Neutron flavor to let the operator recreate it."
            )

        current_description = get_value(flavor, "description", default="")
        description_changed = clean_flavor_description(
            current_description
        ) != clean_flavor_description(description)
        marker_missing = not flavor_description_has_marker(current_description)
        current_is_enabled = bool(get_value(flavor, "is_enabled", default=True))
        is_enabled_drifted = current_is_enabled != is_enabled

        if is_enabled_drifted:
            LOG.info(
                "Router flavor %s is_enabled drift: have=%s want=%s; reconciling",
                name,
                current_is_enabled,
                is_enabled,
            )

        if description_changed or marker_missing or is_enabled_drifted:
            return conn.network.update_flavor(
                flavor,
                description=managed_description,
                is_enabled=is_enabled,
            )
        return flavor

    return create.create_flavor(
        conn, name, service_type, description, is_enabled=is_enabled
    )


def render_flavor(flavor: Any) -> dict[str, Any]:
    return {
        "id": get_value(flavor, "id"),
        "name": get_value(flavor, "name"),
        "service_type": get_value(flavor, "service_type"),
        "description": get_value(flavor, "description"),
        "is_enabled": get_value(flavor, "is_enabled"),
        "service_profile_ids": service_profile_ids(flavor),
    }


def sync_flavor(
    conn: Any,
    flavor_config: dict[str, Any],
    profile_cache: create.ServiceProfileCache,
) -> None:
    """Reconcile one router flavor CR to the desired Neutron state.

    ``flavor_config`` is the CR spec after cloudCredentialsRef has been
    stripped. Schema-required keys are read via subscript so a missing key
    fails loudly rather than being silently defaulted; schema-optional keys
    (description, meta_info) fall back to their type's empty value.
    """
    name = flavor_config["name"]
    service_type = flavor_config.get("service_type", DEFAULT_SERVICE_TYPE)
    description = flavor_config.get("description", "")
    is_enabled = flavor_config["is_enabled"]
    profile_specs = flavor_config["service_profiles"]

    LOG.info(
        "Reconciling router flavor %s with %s service profile(s)",
        name,
        len(profile_specs),
    )
    desired_profiles = [
        create.ensure_profile(conn, name, profile_spec, profile_cache)
        for profile_spec in profile_specs
    ]
    flavor = ensure_flavor(conn, name, service_type, description, is_enabled=is_enabled)
    flavor = create.reconcile_flavor_profiles(conn, flavor, desired_profiles)
    LOG.info(
        "Reconciled router flavor: %s",
        json.dumps(render_flavor(flavor), sort_keys=True),
    )
