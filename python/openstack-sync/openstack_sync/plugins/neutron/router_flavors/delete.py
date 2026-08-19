"""Delete/prune logic for removed Neutron router flavors."""

from __future__ import annotations

import logging
from typing import Any

from openstack_sync.plugins.common import get_service_profile
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import is_conflict
from openstack_sync.plugins.common import is_not_found
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.common import service_profile_ids
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    DEFAULT_SERVICE_TYPE,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    DELETE_UNUSED_SERVICE_PROFILES,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    PRUNE_DRIVER_PREFIXES,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    PRUNE_REMOVED_FLAVORS,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    is_managed_flavor,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    is_managed_service_profile,
)

LOG = logging.getLogger(__name__)


def configured_service_profile_ids(flavors: list[dict[str, Any]]) -> set[str]:
    return {
        str(flavor_config["profile_id"])
        for flavor_config in flavors
        if flavor_config.get("profile_id")
    }


def configured_flavor_names(flavors: list[dict[str, Any]]) -> set[str]:
    return {
        str(flavor_config["name"])
        for flavor_config in flavors
        if flavor_config.get("name")
    }


def service_profile_driver(profile: Any) -> str:
    return str(get_value(profile, "driver", default=""))


def get_cached_service_profile(
    conn: Any,
    profile_id: str,
    profile_cache: dict[str, Any | None],
) -> Any | None:
    if profile_id not in profile_cache:
        profile_cache[profile_id] = get_service_profile(conn, profile_id)
    return profile_cache[profile_id]


def is_prunable_service_profile(profile: Any) -> bool:
    driver = service_profile_driver(profile)
    return bool(PRUNE_DRIVER_PREFIXES) and any(
        driver.startswith(prefix) for prefix in PRUNE_DRIVER_PREFIXES
    )


def is_prunable_flavor(conn: Any, flavor: Any) -> bool:
    if get_value(flavor, "service_type") != DEFAULT_SERVICE_TYPE:
        return False
    return is_managed_flavor(flavor)


def flavor_has_routers(conn: Any, flavor: Any) -> bool:
    flavor_id = resource_id(flavor)
    flavor_name = get_value(flavor, "name", default=flavor_id)

    try:
        routers = list(conn.network.routers(flavor_id=flavor_id))
    except Exception as exc:
        LOG.warning(
            "Unable to check routers for removed router flavor %s; "
            "skipping deletion: %s",
            flavor_name,
            exc,
        )
        return True

    if routers:
        LOG.info(
            "Router flavor %s is still used by %s router(s); skipping deletion",
            flavor_name,
            len(routers),
        )
        return True

    return False


def service_profile_attached_to_any_flavor(conn: Any, profile_id: str) -> bool:
    for flavor in conn.network.flavors(service_type=DEFAULT_SERVICE_TYPE):
        if profile_id in service_profile_ids(flavor):
            return True
    return False


def maybe_delete_service_profile(
    conn: Any,
    profile_id: str,
    protected_profile_ids: set[str],
    profile_cache: dict[str, Any | None],
) -> None:
    if not DELETE_UNUSED_SERVICE_PROFILES:
        LOG.info("Keeping service profile %s; profile pruning is disabled", profile_id)
        return

    if profile_id in protected_profile_ids:
        LOG.info(
            "Keeping service profile %s; it is configured by current router flavor "
            "config",
            profile_id,
        )
        return

    profile = get_cached_service_profile(conn, profile_id, profile_cache)
    if not profile:
        return

    if not is_prunable_service_profile(profile):
        LOG.info(
            "Keeping service profile %s; driver %s is outside prune scope",
            profile_id,
            service_profile_driver(profile),
        )
        return

    if not is_managed_service_profile(profile):
        LOG.info("Keeping service profile %s; it is not operator-managed", profile_id)
        return

    if service_profile_attached_to_any_flavor(conn, profile_id):
        LOG.info("Keeping service profile %s; it is still attached", profile_id)
        return

    LOG.info("Deleting unused service profile %s", profile_id)
    try:
        conn.network.delete_service_profile(profile, ignore_missing=True)
        profile_cache[profile_id] = None
    except Exception as exc:
        if is_not_found(exc):
            profile_cache[profile_id] = None
            return
        if is_conflict(exc):
            LOG.info("Service profile %s is still in use; skipping delete", profile_id)
            return
        raise


def delete_removed_flavor(
    conn: Any,
    flavor: Any,
    protected_profile_ids: set[str],
    profile_cache: dict[str, Any | None],
) -> None:
    flavor_id = resource_id(flavor)
    flavor_name = get_value(flavor, "name", default=flavor_id)
    profile_ids = service_profile_ids(flavor)

    if flavor_has_routers(conn, flavor):
        return

    LOG.info("Deleting removed router flavor %s (%s)", flavor_name, flavor_id)
    try:
        conn.network.delete_flavor(flavor, ignore_missing=True)
    except Exception as exc:
        if is_not_found(exc):
            return
        if is_conflict(exc):
            LOG.info(
                "Router flavor %s is still in use; skipping delete",
                flavor_name,
            )
            return
        raise

    for profile_id in profile_ids:
        maybe_delete_service_profile(
            conn, profile_id, protected_profile_ids, profile_cache
        )


def prune_orphaned_service_profiles(
    conn: Any,
    protected_profile_ids: set[str],
    profile_cache: dict[str, Any | None],
) -> None:
    """Delete orphaned operator-managed service profiles.

    Runs after the flavor prune loop to catch profiles left behind when
    delete_flavor succeeded but maybe_delete_service_profile threw on the same
    run. Safe to run every cycle because it only touches operator-owned, unattached
    profiles.
    """
    LOG.info("Scanning for orphaned operator-managed service profiles")
    for profile in list(conn.network.service_profiles()):
        profile_id = resource_id(profile)
        if not is_prunable_service_profile(profile):
            continue
        if not is_managed_service_profile(profile):
            continue
        maybe_delete_service_profile(
            conn, profile_id, protected_profile_ids, profile_cache
        )


def prune_removed_flavors(
    conn: Any,
    flavors: list[dict[str, Any]],
    *,
    authoritative_empty_desired: bool = False,
) -> None:
    if not PRUNE_REMOVED_FLAVORS:
        LOG.info("Router flavor pruning is disabled")
        return

    if not flavors and not authoritative_empty_desired:
        LOG.warning(
            "No desired router flavors found; skipping prune to avoid deleting "
            "all managed router flavors"
        )
        return

    desired_names = configured_flavor_names(flavors)
    protected_profile_ids = configured_service_profile_ids(flavors)
    profile_cache: dict[str, Any | None] = {}

    LOG.info("Pruning removed router flavors")
    for flavor in list(conn.network.flavors(service_type=DEFAULT_SERVICE_TYPE)):
        flavor_name = get_value(flavor, "name")
        if not flavor_name or flavor_name in desired_names:
            continue
        if not is_prunable_flavor(conn, flavor):
            continue
        delete_removed_flavor(conn, flavor, protected_profile_ids, profile_cache)

    # Second pass: catch profiles orphaned by a partial failure on a previous
    # run (delete_flavor succeeded but maybe_delete_service_profile threw).
    prune_orphaned_service_profiles(conn, protected_profile_ids, profile_cache)
