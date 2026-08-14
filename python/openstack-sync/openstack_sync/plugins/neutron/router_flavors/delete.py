"""Delete/prune logic for removed Neutron router flavors."""

from __future__ import annotations

import logging
from collections import Counter
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
    delete_unused_service_profiles_enabled,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    is_managed_flavor,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    is_managed_service_profile,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    prune_driver_prefixes,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    prune_removed_flavors_enabled,
)

LOG = logging.getLogger(__name__)


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
    prefixes = prune_driver_prefixes()
    return bool(prefixes) and any(driver.startswith(prefix) for prefix in prefixes)


def is_prunable_flavor(flavor: Any) -> bool:
    if get_value(flavor, "service_type") != DEFAULT_SERVICE_TYPE:
        return False
    return is_managed_flavor(flavor)


def service_profile_attachment_counts(flavors: list[Any]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for flavor in flavors:
        counts.update(set(service_profile_ids(flavor)))
    return counts


def detach_service_profile_ids(
    profile_attachment_counts: Counter[str],
    profile_ids: list[str],
) -> None:
    for profile_id in profile_ids:
        profile_attachment_counts[profile_id] -= 1
        if profile_attachment_counts[profile_id] <= 0:
            del profile_attachment_counts[profile_id]


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


def service_profile_attached_to_any_flavor(
    profile_attachment_counts: Counter[str],
    profile_id: str,
) -> bool:
    return profile_attachment_counts[profile_id] > 0


def maybe_delete_service_profile(
    conn: Any,
    profile_id: str,
    profile_cache: dict[str, Any | None],
    profile_attachment_counts: Counter[str],
) -> None:
    if not delete_unused_service_profiles_enabled():
        LOG.info("Keeping service profile %s; profile pruning is disabled", profile_id)
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

    if service_profile_attached_to_any_flavor(profile_attachment_counts, profile_id):
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
    profile_cache: dict[str, Any | None],
    profile_attachment_counts: Counter[str],
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
            LOG.info("Router flavor %s (%s) is already absent", flavor_name, flavor_id)
        elif is_conflict(exc):
            LOG.info(
                "Router flavor %s is still in use; skipping delete",
                flavor_name,
            )
            return
        else:
            raise

    detach_service_profile_ids(profile_attachment_counts, profile_ids)

    for profile_id in profile_ids:
        maybe_delete_service_profile(
            conn,
            profile_id,
            profile_cache,
            profile_attachment_counts,
        )


def prune_orphaned_service_profiles(
    conn: Any,
    profile_cache: dict[str, Any | None],
    profile_attachment_counts: Counter[str],
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
            conn,
            profile_id,
            profile_cache,
            profile_attachment_counts,
        )


def prune_removed_flavors(
    conn: Any,
    flavors: list[dict[str, Any]],
    *,
    authoritative_empty_desired: bool = False,
) -> None:
    if not prune_removed_flavors_enabled():
        LOG.info("Router flavor pruning is disabled")
        return

    if not flavors and not authoritative_empty_desired:
        LOG.warning(
            "No desired router flavors found; skipping prune to avoid deleting "
            "all managed router flavors"
        )
        return

    desired_names = configured_flavor_names(flavors)
    profile_cache: dict[str, Any | None] = {}

    LOG.info("Pruning removed router flavors")
    current_flavors = list(conn.network.flavors(service_type=DEFAULT_SERVICE_TYPE))
    profile_attachment_counts = service_profile_attachment_counts(current_flavors)
    for flavor in current_flavors:
        flavor_name = get_value(flavor, "name")
        if not flavor_name or flavor_name in desired_names:
            continue
        if not is_prunable_flavor(flavor):
            continue
        delete_removed_flavor(
            conn,
            flavor,
            profile_cache,
            profile_attachment_counts,
        )

    # Second pass: catch profiles orphaned by a partial failure on a previous
    # run (delete_flavor succeeded but maybe_delete_service_profile threw).
    prune_orphaned_service_profiles(
        conn,
        profile_cache,
        profile_attachment_counts,
    )
