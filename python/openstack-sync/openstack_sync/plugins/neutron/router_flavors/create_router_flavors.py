"""Create helpers for Neutron router flavors and service profiles."""

from __future__ import annotations

from typing import Any

from . import router_flavors_common as common


def find_matching_profile(conn: Any, driver: str, meta_info: Any) -> Any | None:
    matching_profiles = []
    for profile in conn.network.service_profiles():
        if common.get_value(profile, "driver", "Driver", default="") != driver:
            continue

        if common.meta_info_matches(
            common.service_profile_meta_info(profile),
            meta_info,
        ):
            matching_profiles.append(profile)

    for profile in matching_profiles:
        if common.is_managed_service_profile(profile):
            return profile

    return matching_profiles[0] if matching_profiles else None


def ensure_profile(
    conn: Any,
    name: str,
    driver: str,
    description: str,
    meta_info: Any,
    configured_profile_id: str,
) -> Any:
    if configured_profile_id:
        profile = common.get_service_profile(conn, configured_profile_id)
        if profile:
            common.log(
                f"Using configured service profile {configured_profile_id} for {name}"
            )
            return profile

        common.log(
            f"Configured service profile {configured_profile_id} "
            f"for {name} was not found"
        )

    profile = find_matching_profile(conn, driver, meta_info)
    if profile:
        profile_id = common.resource_id(profile)
        common.log(f"Reusing service profile {profile_id} for {name}")
        # Neutron rejects service profile updates once they are used by
        # service instances. Matching driver/meta_info is enough for
        # idempotent reuse.
        return profile

    service_profile_meta = meta_info
    if not configured_profile_id:
        service_profile_meta = common.managed_meta_info(meta_info)

    common.log(f"Creating service profile for {name} driver={driver}")
    return conn.network.create_service_profile(
        description=description,
        driver=driver,
        meta_info=common.meta_info_payload(service_profile_meta),
        is_enabled=True,
    )


def find_flavor(conn: Any, name: str) -> Any | None:
    for flavor in conn.network.flavors(name=name):
        if common.get_value(flavor, "name", "Name") == name:
            return flavor

    return None


def create_flavor(conn: Any, name: str, service_type: str, description: str) -> Any:
    common.log(f"Creating router flavor {name} service_type={service_type}")
    attrs = {
        "name": name,
        "service_type": service_type,
        "is_enabled": True,
        "description": common.managed_flavor_description(description),
    }
    return conn.network.create_flavor(**attrs)


def ensure_profile_attached(conn: Any, flavor: Any, profile: Any) -> Any:
    flavor = conn.network.get_flavor(flavor)
    flavor_id = common.resource_id(flavor)
    profile_id = common.resource_id(profile)

    if profile_id in common.service_profile_ids(flavor):
        flavor_name = common.get_value(flavor, "name", "Name", default=flavor_id)
        common.log(
            f"Router flavor {flavor_name} already has service profile {profile_id}"
        )
        return flavor

    common.log(f"Binding service profile {profile_id} to router flavor {flavor_id}")
    try:
        conn.network.associate_flavor_with_service_profile(flavor, profile)
    except Exception as exc:
        if not common.is_conflict(exc):
            raise
        common.log(
            f"Router flavor {flavor_id} already has service profile {profile_id}"
        )

    return conn.network.get_flavor(flavor)
