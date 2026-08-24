"""Reconcile a NeutronRouterFlavor CR onto Neutron.

Ordered as the reconcile reads: resolve the service profiles the spec asks for,
converge the flavor itself, then converge the set of profiles bound to it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import get_service_profile
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import meta_info_payload
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.common import service_profile_ids
from openstack_sync.plugins.neutron.router_flavors.markers import (
    clean_flavor_description,
)
from openstack_sync.plugins.neutron.router_flavors.markers import (
    flavor_description_has_marker,
)
from openstack_sync.plugins.neutron.router_flavors.markers import (
    is_managed_service_profile,
)
from openstack_sync.plugins.neutron.router_flavors.markers import (
    managed_flavor_description,
)
from openstack_sync.plugins.neutron.router_flavors.markers import managed_meta_info
from openstack_sync.plugins.neutron.router_flavors.markers import meta_info_matches
from openstack_sync.plugins.neutron.router_flavors.markers import (
    service_profile_meta_info,
)

LOG = logging.getLogger(__name__)

#: Service profiles already fetched this run, keyed by driver.
ProfileCache = dict[str, list[Any]]


@dataclass(frozen=True)
class ProfileDrift:
    """One field of a reused service profile that diverged from the CR spec.

    Profile drift is reported, never auto-corrected. Neutron's
    ``update_service_profile`` calls ``_ensure_service_profile_not_in_use`` and
    raises ``ServiceProfileInUse`` (HTTP 409) while *any* flavor binding exists
    -- not merely while a router is using it -- and this operator binds every
    profile it manages. An update attempt would fail every cycle. Correcting
    drift means unbinding the profile from every flavor first, which is an
    operator decision.
    """

    profile_id: str
    field: str
    have: Any
    want: Any

    def describe(self) -> str:
        return (
            f"service profile {self.profile_id} {self.field}: "
            f"have={self.have!r} want={self.want!r}"
        )


# ---------------------------------------------------------------------------
# Service profiles
# ---------------------------------------------------------------------------


def profiles_for_driver(conn: Any, driver: str, cache: ProfileCache) -> list[Any]:
    """Return every service profile for *driver*, fetched once per run."""
    if driver not in cache:
        cache[driver] = list(conn.network.service_profiles(driver=driver))
    return cache[driver]


def find_matching_profile(profiles: list[Any], meta_info: Any) -> Any | None:
    """Return a service profile matching *meta_info*, preferring owned profiles.

    A NeutronRouterFlavor CR is an ownership claim for the flavor and the service
    profiles described under it. If a matching profile already exists without
    the marker, ``ensure_profile`` adopts it before binding or pruning depends on
    that marker.
    """
    unowned_match: Any | None = None
    for profile in profiles:
        if not meta_info_matches(service_profile_meta_info(profile), meta_info):
            continue
        if is_managed_service_profile(profile):
            return profile
        if unowned_match is None:
            unowned_match = profile
    return unowned_match


def adopt_profile(
    conn: Any, profile: Any, flavor_name: str, spec: dict[str, Any]
) -> Any:
    """Stamp ownership markers onto an existing matching service profile."""
    profile_id = resource_id(profile)
    LOG.info(
        "Adopting existing service profile %s for %s driver=%s",
        profile_id,
        flavor_name,
        spec["driver"],
    )
    try:
        return conn.network.update_service_profile(
            profile,
            description=spec.get("description", ""),
            meta_info=meta_info_payload(managed_meta_info(spec.get("meta_info", {}))),
            is_enabled=spec["is_enabled"],
        )
    except openstack_exceptions.ConflictException as exc:
        raise ConfigError(
            f"Service profile {profile_id!r} matches router flavor {flavor_name!r} "
            "but is not operator-owned, and Neutron rejected adding the ownership "
            "marker because the profile is bound to a flavor. Unbind it from every "
            "flavor or delete it so the operator can recreate it."
        ) from exc


def _profile_drift(
    profile: Any, profile_id: str, flavor_name: str, spec: dict[str, Any]
) -> list[ProfileDrift]:
    """Return the spec fields a reused *profile* disagrees with.

    ``meta_info`` is excluded by construction -- the profile was selected by
    matching it -- and ``driver`` is excluded because profiles are queried per
    driver. That leaves ``is_enabled`` and ``description``.

    ``is_enabled`` is the consequential one: Neutron's
    ``get_flavor_next_provider`` raises ``ServiceProfileDisabled`` (HTTP 503)
    when the profile it selects is disabled, so every router create against the
    flavor fails while the flavor still looks healthy.
    """
    checks = (
        (
            "is_enabled",
            bool(get_value(profile, "is_enabled", default=True)),
            bool(spec["is_enabled"]),
        ),
        (
            "description",
            str(get_value(profile, "description", default="")),
            str(spec.get("description", "")),
        ),
    )
    drift = [
        ProfileDrift(profile_id=profile_id, field=field, have=have, want=want)
        for field, have, want in checks
        if have != want
    ]

    for item in drift:
        LOG.warning(
            "Service profile %s reused by router flavor %s has drifted from the "
            "CR spec (%s: have=%r want=%r). Neutron rejects updates to a profile "
            "bound to any flavor, so the operator cannot correct this; unbind it "
            "from every flavor to update it, or delete it and let the operator "
            "recreate it",
            profile_id,
            flavor_name,
            item.field,
            item.have,
            item.want,
        )
    return drift


def ensure_profile(
    conn: Any,
    flavor_name: str,
    spec: dict[str, Any],
    cache: ProfileCache,
    drift: list[ProfileDrift],
) -> Any:
    """Find or create the service profile *spec* describes.

    The CRD guarantees ``driver`` and ``is_enabled`` are present; ``description``
    and ``meta_info`` are optional and fall back to empty. Drift on a reused
    profile is appended to *drift* -- this is the only place holding both the
    desired spec value and the Neutron state, so it is the only place drift can
    be detected.
    """
    driver = spec["driver"]
    meta_info = spec.get("meta_info", {})

    profiles = profiles_for_driver(conn, driver, cache)
    profile = find_matching_profile(profiles, meta_info)
    if profile:
        profile_id = resource_id(profile)
        if not is_managed_service_profile(profile):
            adopted = adopt_profile(conn, profile, flavor_name, spec)
            for index, candidate in enumerate(profiles):
                if resource_id(candidate) == profile_id:
                    profiles[index] = adopted
                    break
            return adopted
        LOG.info(
            "Reusing service profile %s for %s driver=%s",
            profile_id,
            flavor_name,
            driver,
        )
        drift.extend(_profile_drift(profile, profile_id, flavor_name, spec))
        return profile

    LOG.info(
        "Creating service profile for %s driver=%s is_enabled=%s",
        flavor_name,
        driver,
        spec["is_enabled"],
    )
    created = conn.network.create_service_profile(
        description=spec.get("description", ""),
        driver=driver,
        meta_info=meta_info_payload(managed_meta_info(meta_info)),
        is_enabled=spec["is_enabled"],
    )
    # Visible to any later flavor this run with an identical (driver, meta_info)
    # spec, so it reuses this profile instead of creating a duplicate.
    profiles.append(created)
    return created


# ---------------------------------------------------------------------------
# The flavor
# ---------------------------------------------------------------------------


def find_flavor(conn: Any, name: str) -> Any | None:
    """Return the flavor named *name*, or None.

    The SDK passes ``name=`` as a server-side query parameter which Neutron
    filters in SQL, so at most one record comes back; the equality check guards
    against a future change to substring semantics.
    """
    for flavor in conn.network.flavors(name=name):
        if get_value(flavor, "name") == name:
            return flavor
    return None


def ensure_flavor(conn: Any, spec: dict[str, Any]) -> Any:
    """Find or create the router flavor *spec* describes, reconciling drift."""
    name = spec["name"]
    service_type = spec["service_type"]
    description = spec.get("description", "")
    is_enabled = spec["is_enabled"]

    flavor = find_flavor(conn, name)
    if not flavor:
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

    LOG.info("Router flavor %s already exists", name)
    current_service_type = get_value(flavor, "service_type", default="")
    if current_service_type != service_type:
        raise ConfigError(
            f"Router flavor {name!r} already exists in Neutron with "
            f"service_type={current_service_type!r}; expected {service_type!r}. "
            f"Neutron does not allow updating service_type on an existing "
            f"flavor. Rename the CR or remove the existing Neutron flavor to "
            f"let the operator recreate it."
        )

    current_description = get_value(flavor, "description", default="")
    current_is_enabled = bool(get_value(flavor, "is_enabled", default=True))
    description_changed = clean_flavor_description(
        current_description
    ) != clean_flavor_description(description)
    marker_missing = not flavor_description_has_marker(current_description)
    is_enabled_changed = current_is_enabled != is_enabled

    if is_enabled_changed:
        LOG.info(
            "Router flavor %s is_enabled drift: have=%s want=%s; reconciling",
            name,
            current_is_enabled,
            is_enabled,
        )

    if description_changed or marker_missing or is_enabled_changed:
        return conn.network.update_flavor(
            flavor,
            description=managed_flavor_description(description),
            is_enabled=is_enabled,
        )
    return flavor


# ---------------------------------------------------------------------------
# Flavor <-> profile bindings
# ---------------------------------------------------------------------------


def _associate(conn: Any, flavor: Any, profile: Any) -> None:
    flavor_id = resource_id(flavor)
    profile_id = resource_id(profile)
    LOG.info("Binding service profile %s to router flavor %s", profile_id, flavor_id)
    try:
        conn.network.associate_flavor_with_service_profile(flavor, profile)
    except openstack_exceptions.ConflictException:
        # Another reconcile bound it first.
        LOG.info(
            "Router flavor %s already has service profile %s", flavor_id, profile_id
        )


def _disassociate(conn: Any, flavor: Any, profile: Any) -> None:
    flavor_id = resource_id(flavor)
    profile_id = resource_id(profile)
    LOG.info(
        "Unbinding operator-managed service profile %s from router flavor %s",
        profile_id,
        flavor_id,
    )
    try:
        conn.network.disassociate_flavor_from_service_profile(flavor, profile)
    except openstack_exceptions.NotFoundException:
        LOG.info(
            "Service profile %s already absent from router flavor %s",
            profile_id,
            flavor_id,
        )
    except openstack_exceptions.ConflictException:
        LOG.warning(
            "Cannot unbind service profile %s from router flavor %s (Neutron "
            "reports conflict, likely in use); leaving it attached",
            profile_id,
            flavor_id,
        )


def reconcile_flavor_profiles(
    conn: Any, flavor: Any, desired_profiles: list[Any]
) -> Any:
    """Converge the set of service profiles bound to *flavor*.

    Profiles missing from the flavor are bound; operator-owned profiles bound to
    it but absent from the desired set are unbound. Profiles attached
    out-of-band are left alone -- the operator only unbinds what it owns.
    """
    flavor = conn.network.get_flavor(flavor)
    flavor_name = get_value(flavor, "name", default=resource_id(flavor))

    desired_by_id = {resource_id(p): p for p in desired_profiles}
    current_ids = set(service_profile_ids(flavor))
    to_bind = set(desired_by_id) - current_ids
    to_unbind = current_ids - set(desired_by_id)

    if not to_bind and not to_unbind:
        LOG.info(
            "Router flavor %s already has the desired service profiles %s",
            flavor_name,
            sorted(current_ids),
        )
        return flavor

    for profile_id in sorted(to_bind):
        _associate(conn, flavor, desired_by_id[profile_id])

    for profile_id in sorted(to_unbind):
        profile = get_service_profile(conn, profile_id)
        if profile is None:
            LOG.info(
                "Service profile %s already absent from Neutron; nothing to unbind",
                profile_id,
            )
            continue
        if not is_managed_service_profile(profile):
            LOG.info(
                "Keeping unowned service profile %s on router flavor %s; the "
                "operator only unbinds profiles it owns",
                profile_id,
                flavor_name,
            )
            continue
        _disassociate(conn, flavor, profile)

    return conn.network.get_flavor(flavor)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def render_flavor(flavor: Any) -> dict[str, Any]:
    """Return the reconciled flavor as a loggable dict."""
    return {
        "id": get_value(flavor, "id"),
        "name": get_value(flavor, "name"),
        "service_type": get_value(flavor, "service_type"),
        "description": get_value(flavor, "description"),
        "is_enabled": get_value(flavor, "is_enabled"),
        "service_profile_ids": service_profile_ids(flavor),
    }


def sync_flavor(conn: Any, spec: dict[str, Any], cache: ProfileCache) -> list[str]:
    """Converge one NeutronRouterFlavor spec, returning drift notes."""
    name = spec["name"]
    profile_specs = spec["service_profiles"]

    LOG.info(
        "Reconciling router flavor %s with %s service profile(s)",
        name,
        len(profile_specs),
    )
    drift: list[ProfileDrift] = []
    desired_profiles = [
        ensure_profile(conn, name, profile_spec, cache, drift)
        for profile_spec in profile_specs
    ]
    flavor = ensure_flavor(conn, spec)
    flavor = reconcile_flavor_profiles(conn, flavor, desired_profiles)
    LOG.info(
        "Reconciled router flavor: %s",
        json.dumps(render_flavor(flavor), sort_keys=True),
    )
    return [item.describe() for item in drift]
