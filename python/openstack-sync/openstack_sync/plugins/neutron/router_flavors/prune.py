"""Delete router flavors and service profiles whose CR was removed.

Everything here is gated on the operator's ownership markers, so a flavor or
profile created by hand is never touched. Ownership is the only gate needed: a
resource carrying the marker was created by this operator, which makes any
further filtering redundant.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.common import get_service_profile
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.common import service_profile_ids
from openstack_sync.plugins.neutron.router_flavors.config import SERVICE_TYPE
from openstack_sync.plugins.neutron.router_flavors.markers import is_managed_flavor
from openstack_sync.plugins.neutron.router_flavors.markers import (
    is_managed_service_profile,
)

LOG = logging.getLogger(__name__)

#: Service profiles fetched during a prune, keyed by ID. None means "gone".
ProfileCache = dict[str, Any | None]


def _cached_profile(conn: Any, profile_id: str, cache: ProfileCache) -> Any | None:
    if profile_id not in cache:
        cache[profile_id] = get_service_profile(conn, profile_id)
    return cache[profile_id]


def _attachment_counts(flavors: list[Any]) -> Counter[str]:
    """Count how many flavors each service profile is bound to."""
    counts: Counter[str] = Counter()
    for flavor in flavors:
        counts.update(set(service_profile_ids(flavor)))
    return counts


def _flavor_has_routers(conn: Any, flavor: Any, flavor_name: str) -> bool:
    """Return True when routers still use *flavor*, or when we cannot tell."""
    try:
        routers = list(conn.network.routers(flavor_id=resource_id(flavor)))
    except Exception as exc:  # noqa: BLE001
        LOG.warning(
            "Unable to check routers for router flavor %s; skipping deletion: %s",
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


def maybe_delete_profile(
    conn: Any, profile_id: str, cache: ProfileCache, counts: Counter[str]
) -> None:
    """Delete *profile_id* when the operator owns it and nothing is bound to it."""
    profile = _cached_profile(conn, profile_id, cache)
    if not profile:
        return
    if not is_managed_service_profile(profile):
        LOG.info("Keeping service profile %s; it is not operator-owned", profile_id)
        return
    if counts[profile_id] > 0:
        LOG.info("Keeping service profile %s; it is still attached", profile_id)
        return

    LOG.info("Deleting unused service profile %s", profile_id)
    try:
        conn.network.delete_service_profile(profile, ignore_missing=True)
        cache[profile_id] = None
    except openstack_exceptions.NotFoundException:
        cache[profile_id] = None
    except openstack_exceptions.ConflictException:
        LOG.info("Service profile %s is still in use; skipping delete", profile_id)


def _delete_flavor(
    conn: Any, flavor: Any, cache: ProfileCache, counts: Counter[str]
) -> None:
    flavor_id = resource_id(flavor)
    flavor_name = get_value(flavor, "name", default=flavor_id)
    profile_ids = service_profile_ids(flavor)

    if _flavor_has_routers(conn, flavor, flavor_name):
        return

    LOG.info("Deleting removed router flavor %s (%s)", flavor_name, flavor_id)
    try:
        conn.network.delete_flavor(flavor, ignore_missing=True)
    except openstack_exceptions.NotFoundException:
        LOG.info("Router flavor %s (%s) is already absent", flavor_name, flavor_id)
    except openstack_exceptions.ConflictException:
        LOG.info("Router flavor %s is still in use; skipping delete", flavor_name)
        return

    # The flavor is gone, so its profiles lost one attachment each.
    for profile_id in profile_ids:
        counts[profile_id] -= 1
        if counts[profile_id] <= 0:
            del counts[profile_id]

    for profile_id in profile_ids:
        maybe_delete_profile(conn, profile_id, cache, counts)


def _prune_orphaned_profiles(
    conn: Any, cache: ProfileCache, counts: Counter[str]
) -> None:
    """Delete owned, unattached profiles left behind by an earlier partial failure.

    Safe to run every cycle: it only ever touches operator-owned profiles that
    no flavor is bound to.
    """
    LOG.info("Scanning for orphaned operator-owned service profiles")
    for profile in list(conn.network.service_profiles()):
        if is_managed_service_profile(profile):
            maybe_delete_profile(conn, resource_id(profile), cache, counts)


def prune_removed_flavors(
    conn: Any,
    desired_specs: list[dict[str, Any]],
    *,
    authoritative_empty: bool = False,
) -> None:
    """Delete operator-owned router flavors absent from *desired_specs*.

    An empty *desired_specs* is only acted on when *authoritative_empty* says a
    CR really was deleted; otherwise it may be a snapshot we could not read, and
    pruning against it would delete every managed flavor.
    """
    if not desired_specs and not authoritative_empty:
        LOG.warning(
            "No desired router flavors found; skipping prune to avoid deleting "
            "all managed router flavors"
        )
        return

    desired_names = {str(spec["name"]) for spec in desired_specs if spec.get("name")}
    cache: ProfileCache = {}

    LOG.info("Pruning removed router flavors")
    current = list(conn.network.flavors(service_type=SERVICE_TYPE))
    counts = _attachment_counts(current)
    for flavor in current:
        name = get_value(flavor, "name")
        if not name or name in desired_names:
            continue
        if not is_managed_flavor(flavor):
            continue
        _delete_flavor(conn, flavor, cache, counts)

    _prune_orphaned_profiles(conn, cache, counts)
