"""Reconcile a NeutronSegmentRange CR onto Neutron.

Match a range by ``spec.name`` (project-scoped when unshared), adopting an
existing one or creating it, then update ``minimum``/``maximum``. A legacy
``understack-sr:<name>`` range is renamed in place. Ranges are never deleted.

Only ``name``, ``minimum`` and ``maximum`` are PUT-able in Neutron; a mismatch
on any other field fails the CR.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.neutron.segment_ranges.config import PHYSICAL_NETWORK_TYPES
from openstack_sync.plugins.neutron.segment_ranges.config import TUNNEL_NETWORK_TYPES

LOG = logging.getLogger(__name__)

#: Prefix earlier releases stamped on every operator-created range name. Used
#: only to find and rename those ranges on upgrade; nothing new is created with
#: it. Safe to remove once every deployment has reconciled past this release.
LEGACY_NAME_PREFIX = "understack-sr:"

#: Identity of a range within one credential group: ``(name, project_id)``,
#: where ``project_id`` is ``None`` for a shared spec.
RangeKey = tuple[str, str | None]

#: Segment ranges already fetched this run, keyed by :data:`RangeKey`.
RangeCache = dict[RangeKey, Any]


def _cache_key(spec: dict[str, Any]) -> RangeKey:
    """Return the cache key for *spec*, scoped the same way as its lookup.

    The key must carry every field the Neutron query filters on. An unshared
    spec is looked up by ``name`` and ``project_id``, so two projects can each
    hold a range with the same name; keying by name alone would hand one
    project's range to the other project's CR. A shared spec is looked up by
    name only, so its key has no project.
    """
    name = str(spec["name"])
    if spec.get("shared", True):
        return (name, None)
    return (name, spec.get("project_id"))


def _validate_spec(spec: dict[str, Any]) -> None:
    """Reject a spec whose physical_network does not match its network_type.

    The CRD constrains ranges but cannot express the cross-field rule that VLAN
    ranges need a physical network while tunnelled types must not carry one.
    Enforce it here so a bad spec fails its own CR by name rather than
    reaching Neutron and erroring in a way that is harder to attribute.
    """
    network_type = spec["network_type"]
    physical_network = spec.get("physical_network")
    minimum = int(spec["minimum"])
    maximum = int(spec["maximum"])

    if minimum > maximum:
        raise ConfigError(
            f"minimum {minimum} is greater than maximum {maximum}; "
            "the range is empty"
        )

    if network_type in PHYSICAL_NETWORK_TYPES and not physical_network:
        raise ConfigError(
            f"network_type {network_type!r} requires physical_network to be set"
        )
    if network_type in TUNNEL_NETWORK_TYPES and physical_network:
        raise ConfigError(
            f"network_type {network_type!r} must not set physical_network "
            f"(got {physical_network!r})"
        )

    if not spec.get("shared", True) and not spec.get("project_id"):
        raise ConfigError("project_id is required when shared is false")


def _in_scope(segment_range: Any, name: str, project_id: str | None) -> bool:
    """Return True when *segment_range* has *name* and, if given, *project_id*.

    A shared spec (``project_id`` None) matches on name alone, mirroring the
    query :func:`find_range` sends.
    """
    if str(get_value(segment_range, "name", default="")) != name:
        return False
    if not project_id:
        return True
    return get_value(segment_range, "project_id", default=None) == project_id


def _lookup(conn: Any, name: str, project_id: str | None) -> Any | None:
    """Return the single range named *name* in scope, None if absent.

    More than one match is ambiguous and raises rather than guessing which
    range to converge.
    """
    query: dict[str, Any] = {"name": name}
    if project_id:
        query["project_id"] = project_id

    matches = [
        segment_range
        for segment_range in conn.network.network_segment_ranges(**query)
        if _in_scope(segment_range, name, project_id)
    ]
    if len(matches) > 1:
        raise ConfigError(
            f"Segment range name {name!r} matched {len(matches)} ranges; "
            "set spec.project_id to disambiguate"
        )
    return matches[0] if matches else None


def find_range(conn: Any, spec: dict[str, Any], cache: RangeCache) -> Any | None:
    """Return the range the spec names, adopting one created out-of-band.

    Matching is by ``name`` -- the range's own user-facing identity. An
    unshared spec also scopes the match by ``project_id`` so two projects can
    hold same-named ranges without colliding. More than one match is ambiguous
    and raises rather than guessing which range to converge.

    When no range has the plain name, the lookup falls back to the legacy
    ``understack-sr:<name>`` an earlier release created, under the same scope.
    The returned range then still carries the legacy name;
    :func:`sync_segment_range` renames it. The legacy lookup only runs on a
    miss, so a deployment that has already migrated pays no extra API call.

    The scope is passed to Neutron as list filters and then re-checked on each
    returned range, so the match does not depend on the server honouring the
    filters: an admin-scoped or filter-ignoring listing that returns every
    project's same-named range still resolves to this spec's project only.

    The *cache* is shared across a credential group's CRs and keyed by
    :func:`_cache_key`, so a hit always matches the scope the query would have
    used.
    """
    key = _cache_key(spec)
    if key in cache:
        return cache[key]

    name, project_id = key
    match = _lookup(conn, name, project_id)
    if match is None and not name.startswith(LEGACY_NAME_PREFIX):
        match = _lookup(conn, f"{LEGACY_NAME_PREFIX}{name}", project_id)
    if match is not None:
        cache[key] = match
    return match


def _immutable_drift(segment_range: Any, spec: dict[str, Any]) -> str | None:
    """Return a description of any immutable-field mismatch, else None.

    Neutron accepts only ``name``, ``minimum`` and ``maximum`` on a PUT, so
    ``network_type``, ``physical_network``, ``shared`` and ``project_id`` are
    all immutable: a CR that changes any of them, or that adopts an existing
    range built differently, must fail loudly here rather than send a PUT
    Neutron rejects with a bare 400.

    ``physical_network`` is compared as a string with the empty string standing
    for "unset": Neutron's column is non-nullable and it normalizes non-VLAN
    ranges to ``physical_network=''``, while a tunnelled spec omits the field
    entirely. Comparing the raw values would report drift on every reconcile of
    a vxlan/gre/geneve range against its own spec. ``project_id`` is only
    compared for an unshared spec, since Neutron ignores it for a shared range.
    """
    have = {
        "network_type": str(get_value(segment_range, "network_type", default="")),
        "physical_network": str(
            get_value(segment_range, "physical_network", default="")
        ),
        "shared": bool(get_value(segment_range, "shared", default=True)),
    }
    want = {
        "network_type": spec["network_type"],
        "physical_network": spec.get("physical_network") or "",
        "shared": bool(spec.get("shared", True)),
    }
    if not want["shared"]:
        have["project_id"] = get_value(segment_range, "project_id", default=None)
        want["project_id"] = spec.get("project_id")

    for field, have_value in have.items():
        if have_value != want[field]:
            return f"{field}: have={have_value!r} want={want[field]!r}"
    return None


def _mutable_updates(segment_range: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Return the mutable fields that diverge from *spec*, empty when in sync.

    Only ``minimum`` and ``maximum`` are mutable; every other field is handled
    by :func:`_immutable_drift`.
    """
    updates: dict[str, Any] = {}

    have_min = int(get_value(segment_range, "minimum", default=0))
    have_max = int(get_value(segment_range, "maximum", default=0))
    if have_min != int(spec["minimum"]):
        updates["minimum"] = int(spec["minimum"])
    if have_max != int(spec["maximum"]):
        updates["maximum"] = int(spec["maximum"])

    return updates


def _create_kwargs(spec: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "name": str(spec["name"]),
        "network_type": spec["network_type"],
        "minimum": int(spec["minimum"]),
        "maximum": int(spec["maximum"]),
        "shared": bool(spec.get("shared", True)),
    }
    if spec.get("physical_network"):
        kwargs["physical_network"] = spec["physical_network"]
    if not kwargs["shared"] and spec.get("project_id"):
        kwargs["project_id"] = spec["project_id"]
    return kwargs


def render_range(segment_range: Any) -> dict[str, Any]:
    """Return the reconciled range as a loggable dict."""
    return {
        "id": get_value(segment_range, "id"),
        "name": get_value(segment_range, "name"),
        "network_type": get_value(segment_range, "network_type"),
        "physical_network": get_value(segment_range, "physical_network"),
        "minimum": get_value(segment_range, "minimum"),
        "maximum": get_value(segment_range, "maximum"),
        "shared": get_value(segment_range, "shared"),
        "project_id": get_value(segment_range, "project_id"),
    }


def sync_segment_range(conn: Any, spec: dict[str, Any], cache: RangeCache) -> list[str]:
    """Converge one NeutronSegmentRange spec, returning drift notes."""
    _validate_spec(spec)

    name = str(spec["name"])
    existing = find_range(conn, spec, cache)

    if existing is None:
        LOG.info(
            "Creating segment range %s type=%s physical=%s %s-%s",
            name,
            spec["network_type"],
            spec.get("physical_network"),
            spec["minimum"],
            spec["maximum"],
        )
        created = conn.network.create_network_segment_range(**_create_kwargs(spec))
        cache[_cache_key(spec)] = created
        LOG.info(
            "Reconciled segment range: %s",
            json.dumps(render_range(created), sort_keys=True),
        )
        return []

    have_name = str(get_value(existing, "name", default=""))
    legacy = have_name != name
    LOG.info(
        "Reusing segment range %s (%s)%s",
        name,
        resource_id(existing),
        f" found under legacy name {have_name}" if legacy else "",
    )

    # Checked before any rename so a legacy range built differently fails the
    # CR untouched rather than being renamed and then rejected.
    drift = _immutable_drift(existing, spec)
    if drift:
        found_as = f" (found as legacy {have_name!r})" if legacy else ""
        raise ConfigError(
            f"Segment range {name!r}{found_as} already exists in Neutron with a "
            f"different immutable field ({drift}). Neutron only allows updating "
            "minimum and maximum on an existing range; network_type, "
            "physical_network, shared and project_id are fixed at creation. Rename "
            "the CR or delete the existing range to let the operator recreate it."
        )

    updates = _mutable_updates(existing, spec)
    if legacy:
        # Same PUT as any minimum/maximum drift: one write migrates the range.
        LOG.info("Migrating legacy segment range %s to %s", have_name, name)
        updates["name"] = name
    if not updates:
        LOG.info("Segment range %s already matches the spec", name)
        return []

    LOG.info("Reconciling segment range %s drift: %s", name, sorted(updates))
    updated = conn.network.update_network_segment_range(
        resource_id(existing), **updates
    )
    cache[_cache_key(spec)] = updated
    LOG.info(
        "Reconciled segment range: %s",
        json.dumps(render_range(updated), sort_keys=True),
    )
    return []
