"""Create helpers for Neutron router flavors and service profiles."""

from __future__ import annotations

from typing import Any

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
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import log
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


def find_matching_profile(conn: Any, driver: str, meta_info: Any) -> Any | None:
    matching_profiles = []
    for profile in conn.network.service_profiles():
        if get_value(profile, "driver", "Driver", default="") != driver:
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
    attached to service instances, so we cannot reconcile drift — but we must
    surface it rather than reporting success while spec and reality diverge.
    """
    drift = []
    current_driver = get_value(profile, "driver", "Driver", default="")
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
                log(
                    f"WARNING: service profile {profile_id} for {name} cannot be "
                    f"updated (Neutron rejects updates to in-use profiles). "
                    f"Spec has drifted: {'; '.join(drift)}. "
                    "To apply changes, detach all routers from this flavor, "
                    "remove profile_id from the CR, and re-sync."
                )
            else:
                log(f"Using configured service profile {profile_id} for {name}")
            return profile

        log(
            f"Configured service profile {configured_profile_id} "
            f"for {name} was not found"
        )

    profile = find_matching_profile(conn, driver, meta_info)
    if profile:
        profile_id = resource_id(profile)
        log(f"Reusing service profile {profile_id} for {name}")
        return profile

    service_profile_meta = (
        meta_info if configured_profile_id else managed_meta_info(meta_info)
    )

    log(f"Creating service profile for {name} driver={driver}")
    return conn.network.create_service_profile(
        description=description,
        driver=driver,
        meta_info=meta_info_payload(service_profile_meta),
        is_enabled=True,
    )


def find_flavor(conn: Any, name: str) -> Any | None:
    # The SDK passes name= as a server-side query parameter (?name=<name>),
    # which Neutron filters in SQL — at most one record is returned. The
    # equality check guards against a future change to substring/LIKE semantics.
    for flavor in conn.network.flavors(name=name):
        if get_value(flavor, "name", "Name") == name:
            return flavor
    return None


def create_flavor(conn: Any, name: str, service_type: str, description: str) -> Any:
    log(f"Creating router flavor {name} service_type={service_type}")
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
