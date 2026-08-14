"""Create helpers for Neutron router flavors and service profiles."""

from __future__ import annotations

import logging
from typing import Any

from openstack_sync.plugins.common import get_service_profile
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import is_conflict
from openstack_sync.plugins.common import is_not_found
from openstack_sync.plugins.common import meta_info_payload
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.common import service_profile_ids
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    ProfileDrift,
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
ServiceProfileCache = dict[str, list[Any]]


def list_service_profiles(conn: Any, driver: str) -> list[Any]:
    """Fetch service profiles for a single driver from Neutron."""
    return list(conn.network.service_profiles(driver=driver))


def service_profiles_for_driver(
    conn: Any, driver: str, profile_cache: ServiceProfileCache
) -> list[Any]:
    """Return a credential-group cache entry for service profiles by driver."""
    if driver not in profile_cache:
        profile_cache[driver] = list_service_profiles(conn, driver)
    return profile_cache[driver]


def find_matching_profile(profiles: list[Any], meta_info: Any) -> Any | None:
    """Return the operator-managed profile matching *meta_info*, if any.

    Only operator-owned profiles are reuse candidates.  Reusing a profile the
    operator does not own would bind it to the flavor, and
    ``reconcile_flavor_profiles`` unbinds only profiles carrying the ownership
    marker -- so the operator would have created a binding it can never remove.
    That binding outlives the spec that created it, and Neutron's
    ``get_flavor_next_provider`` selects an arbitrary binding (``objs[0]``), so a
    stale one can end up serving routers with the wrong ``meta_info``.

    An unowned profile that happens to match is therefore left completely
    untouched -- not adopted by stamping the ownership marker onto it, which
    would enrol somebody else's profile into ``prune_orphaned_service_profiles``
    for eventual deletion -- and ``ensure_profile`` creates a dedicated managed
    profile alongside it.
    """
    unowned_matches: list[str] = []
    for profile in profiles:
        if not meta_info_matches(service_profile_meta_info(profile), meta_info):
            continue
        if is_managed_service_profile(profile):
            return profile
        unowned_matches.append(str(get_value(profile, "id", default="<unknown>")))

    if unowned_matches:
        LOG.info(
            "Not reusing service profile(s) %s: they match the desired meta_info "
            "but are not operator-owned, and the operator only binds profiles it "
            "can unbind again; creating a dedicated managed profile instead",
            sorted(unowned_matches),
        )

    return None


def _collect_profile_drift(
    profile: Any,
    profile_id: str,
    driver: str,
    flavor_name: str,
    *,
    description: str,
    is_enabled: bool,
) -> list[ProfileDrift]:
    """Return the spec fields on a reused *profile* that Neutron disagrees on.

    ``meta_info`` is excluded by construction -- the profile was selected by
    matching it -- and ``driver`` is excluded because profiles are queried per
    driver.  That leaves ``is_enabled`` and ``description``.

    ``is_enabled`` is the consequential one: Neutron's
    ``get_flavor_next_provider`` raises ``ServiceProfileDisabled`` (HTTP 503)
    when the selected profile is disabled, so every router create against the
    flavor fails while the flavor itself still looks healthy.
    """
    drifted: list[ProfileDrift] = []

    current_is_enabled = bool(get_value(profile, "is_enabled", default=True))
    if current_is_enabled != bool(is_enabled):
        drifted.append(
            ProfileDrift(
                profile_id=profile_id,
                driver=driver,
                field="is_enabled",
                have=current_is_enabled,
                want=bool(is_enabled),
            )
        )

    current_description = str(get_value(profile, "description", default=""))
    if current_description != str(description):
        drifted.append(
            ProfileDrift(
                profile_id=profile_id,
                driver=driver,
                field="description",
                have=current_description,
                want=str(description),
            )
        )

    for item in drifted:
        LOG.warning(
            "Service profile %s reused by router flavor %s has drifted from the "
            "CR spec (%s). Neutron rejects updates to a profile bound to any "
            "flavor, so the operator cannot correct this; unbind the profile "
            "from every flavor to update it, or delete it and let the operator "
            "recreate it",
            profile_id,
            flavor_name,
            item.describe(),
        )

    return drifted


def ensure_profile(
    conn: Any,
    flavor_name: str,
    profile_spec: dict[str, Any],
    profile_cache: ServiceProfileCache,
    drift: list[ProfileDrift] | None = None,
) -> Any:
    """Find or create a service profile matching *profile_spec*.

    The CR schema guarantees ``driver`` is present and ``is_enabled`` carries
    the CRD default (true). ``description`` and ``meta_info`` are optional in
    the schema; missing values fall back to empty.

    Only operator-owned profiles are reused (see ``find_matching_profile``).
    When a reused profile has drifted from the spec, each drifted field is
    logged and appended to *drift* if a list was supplied, so the caller can
    surface it on the CR status rather than reporting an unqualified success.
    Drift is only ever detected here, because this is the only place that holds
    the desired value from the CR spec.
    """
    driver = profile_spec["driver"]
    description = profile_spec.get("description", "")
    meta_info = profile_spec.get("meta_info", {})
    is_enabled = profile_spec["is_enabled"]

    profiles = service_profiles_for_driver(conn, driver, profile_cache)
    profile = find_matching_profile(profiles, meta_info)
    if profile:
        profile_id = resource_id(profile)
        LOG.info(
            "Reusing service profile %s for %s driver=%s",
            profile_id,
            flavor_name,
            driver,
        )
        drifted = _collect_profile_drift(
            profile,
            profile_id,
            driver,
            flavor_name,
            description=description,
            is_enabled=is_enabled,
        )
        if drift is not None:
            drift.extend(drifted)
        return profile

    LOG.info(
        "Creating service profile for %s driver=%s is_enabled=%s",
        flavor_name,
        driver,
        is_enabled,
    )
    new_profile = conn.network.create_service_profile(
        description=description,
        driver=driver,
        meta_info=meta_info_payload(managed_meta_info(meta_info)),
        is_enabled=is_enabled,
    )
    # Make the new profile visible to any later flavor in this same run that
    # has an identical (driver, meta_info) spec, so it gets reused instead of
    # creating a duplicate profile.
    profiles.append(new_profile)
    return new_profile


def find_flavor(conn: Any, name: str) -> Any | None:
    # The SDK passes name= as a server-side query parameter (?name=<name>),
    # which Neutron filters in SQL, so at most one record is returned. The
    # equality check guards against a future change to substring/LIKE semantics.
    for flavor in conn.network.flavors(name=name):
        if get_value(flavor, "name") == name:
            return flavor
    return None


def create_flavor(
    conn: Any,
    name: str,
    service_type: str,
    description: str,
    *,
    is_enabled: bool,
) -> Any:
    LOG.info(
        "Creating router flavor %s service_type=%s is_enabled=%s",
        name,
        service_type,
        is_enabled,
    )
    return conn.network.create_flavor(
        name=name,
        service_type=service_type,
        is_enabled=is_enabled,
        description=managed_flavor_description(description),
    )


def _associate_profile(conn: Any, flavor: Any, profile: Any) -> None:
    """Associate *profile* with *flavor*, treating a 409 as already-associated."""
    flavor_id = resource_id(flavor)
    profile_id = resource_id(profile)
    LOG.info("Binding service profile %s to router flavor %s", profile_id, flavor_id)
    try:
        conn.network.associate_flavor_with_service_profile(flavor, profile)
    except Exception as exc:  # noqa: BLE001
        if not is_conflict(exc):
            raise
        LOG.info(
            "Router flavor %s already has service profile %s",
            flavor_id,
            profile_id,
        )


def _disassociate_profile(conn: Any, flavor: Any, profile: Any) -> None:
    """Disassociate *profile* from *flavor*, tolerating not-found/conflict."""
    flavor_id = resource_id(flavor)
    profile_id = resource_id(profile)
    LOG.info(
        "Unbinding operator-managed service profile %s from router flavor %s",
        profile_id,
        flavor_id,
    )
    try:
        conn.network.disassociate_flavor_from_service_profile(flavor, profile)
    except Exception as exc:  # noqa: BLE001
        if is_not_found(exc):
            LOG.info(
                "Service profile %s already absent from router flavor %s",
                profile_id,
                flavor_id,
            )
            return
        if is_conflict(exc):
            LOG.warning(
                "Cannot unbind service profile %s from router flavor %s "
                "(Neutron reports conflict, likely in use); leaving attached",
                profile_id,
                flavor_id,
            )
            return
        raise


def reconcile_flavor_profiles(
    conn: Any,
    flavor: Any,
    desired_profiles: list[Any],
) -> Any:
    """Reconcile the set of service profiles bound to *flavor*.

    ``desired_profiles`` is the list resolved from the CR spec (post
    ``ensure_profile``). Profiles missing from the flavor are associated;
    operator-managed profiles present on the flavor but absent from the
    desired set are disassociated. Unmanaged profiles attached out-of-band
    are left untouched so an operator's ad-hoc attachments survive reconcile.

    Returns the flavor re-fetched from Neutron so callers see the current
    ``service_profile_ids``.
    """
    flavor = conn.network.get_flavor(flavor)
    flavor_id = resource_id(flavor)
    flavor_name = get_value(flavor, "name", default=flavor_id)

    desired_by_id: dict[str, Any] = {resource_id(p): p for p in desired_profiles}
    current_ids = set(service_profile_ids(flavor))
    desired_ids = set(desired_by_id)

    to_associate = desired_ids - current_ids
    to_disassociate_candidates = current_ids - desired_ids

    if not to_associate and not to_disassociate_candidates:
        LOG.info(
            "Router flavor %s already has the desired service profiles %s",
            flavor_name,
            sorted(current_ids),
        )
        return flavor

    for profile_id in sorted(to_associate):
        _associate_profile(conn, flavor, desired_by_id[profile_id])

    for profile_id in sorted(to_disassociate_candidates):
        profile = get_service_profile(conn, profile_id)
        if profile is None:
            LOG.info(
                "Service profile %s already absent from Neutron; nothing to unbind",
                profile_id,
            )
            continue
        if not is_managed_service_profile(profile):
            LOG.info(
                "Keeping unmanaged service profile %s on router flavor %s; "
                "operator only unbinds profiles it owns",
                profile_id,
                flavor_name,
            )
            continue
        _disassociate_profile(conn, flavor, profile)

    return conn.network.get_flavor(flavor)
