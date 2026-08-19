"""Create helpers for Neutron router flavors and service profiles."""

from __future__ import annotations

import logging
from typing import Any

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import get_service_profile
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import is_conflict
from openstack_sync.plugins.common import meta_info_payload
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.common import service_profile_ids
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    comparable_meta_info,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    is_managed_service_profile,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    managed_flavor_description,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    managed_meta_info,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    meta_info_matches,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    service_profile_meta_info,
)

LOG = logging.getLogger(__name__)


def find_matching_profile(conn: Any, driver: str, meta_info: Any) -> Any | None:
    matching_profiles = []
    for profile in conn.network.service_profiles():
        if get_value(profile, "driver", default="") != driver:
            continue
        if meta_info_matches(service_profile_meta_info(profile), meta_info):
            matching_profiles.append(profile)

    for profile in matching_profiles:
        if is_managed_service_profile(profile):
            return profile

    return matching_profiles[0] if matching_profiles else None


def _profile_drifted(profile: Any, driver: str, meta_info: Any) -> list[str]:
    """Return drift descriptions between *profile* and the desired spec.

    Neutron rejects ``update_service_profile`` with a 409 once the profile is
    attached to service instances, so we cannot reconcile drift. We still
    surface it rather than reporting success while spec and reality diverge.
    """
    drift = []
    current_driver = get_value(profile, "driver", default="")
    if current_driver != driver:
        drift.append(f"driver: have={current_driver!r} want={driver!r}")

    if not meta_info_matches(service_profile_meta_info(profile), meta_info):
        current_meta = meta_info_payload(
            comparable_meta_info(service_profile_meta_info(profile))
        )
        desired_meta = meta_info_payload(comparable_meta_info(meta_info))
        drift.append(f"meta_info: have={current_meta} want={desired_meta}")

    return drift


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
            profile_id = resource_id(profile)
            drift = _profile_drifted(profile, driver, meta_info)
            if drift:
                LOG.warning(
                    "service profile %s for %s cannot be updated "
                    "(Neutron rejects updates to in-use profiles). "
                    "Spec has drifted: %s. To apply changes, detach all "
                    "routers from this flavor, remove profile_id from the CR, "
                    "and re-sync.",
                    profile_id,
                    name,
                    "; ".join(drift),
                )
            else:
                LOG.info("Using configured service profile %s for %s", profile_id, name)
            return profile

        LOG.error(
            "Configured service profile %s for %s was not found",
            configured_profile_id,
            name,
        )
        raise ConfigError(
            f"Configured service profile {configured_profile_id} "
            f"for {name} was not found"
        )

    profile = find_matching_profile(conn, driver, meta_info)
    if profile:
        profile_id = resource_id(profile)
        LOG.info("Reusing service profile %s for %s", profile_id, name)
        return profile

    LOG.info("Creating service profile for %s driver=%s", name, driver)
    return conn.network.create_service_profile(
        description=description,
        driver=driver,
        meta_info=meta_info_payload(managed_meta_info(meta_info)),
        is_enabled=True,
    )


def find_flavor(conn: Any, name: str) -> Any | None:
    # The SDK passes name= as a server-side query parameter (?name=<name>),
    # which Neutron filters in SQL, so at most one record is returned. The
    # equality check guards against a future change to substring/LIKE semantics.
    for flavor in conn.network.flavors(name=name):
        if get_value(flavor, "name") == name:
            return flavor
    return None


def create_flavor(conn: Any, name: str, service_type: str, description: str) -> Any:
    LOG.info("Creating router flavor %s service_type=%s", name, service_type)
    return conn.network.create_flavor(
        name=name,
        service_type=service_type,
        is_enabled=True,
        description=managed_flavor_description(description),
    )


def ensure_profile_attached(conn: Any, flavor: Any, profile: Any) -> Any:
    flavor = conn.network.get_flavor(flavor)
    flavor_id = resource_id(flavor)
    profile_id = resource_id(profile)

    if profile_id in service_profile_ids(flavor):
        flavor_name = get_value(flavor, "name", default=flavor_id)
        LOG.info(
            "Router flavor %s already has service profile %s",
            flavor_name,
            profile_id,
        )
        return flavor

    LOG.info("Binding service profile %s to router flavor %s", profile_id, flavor_id)
    try:
        conn.network.associate_flavor_with_service_profile(flavor, profile)
    except Exception as exc:
        if not is_conflict(exc):
            raise
        LOG.info(
            "Router flavor %s already has service profile %s",
            flavor_id,
            profile_id,
        )

    return conn.network.get_flavor(flavor)
