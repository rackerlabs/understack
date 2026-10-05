"""Reconcile a NeutronSegmentRange CR onto Neutron.

Find the range the CR describes by its name, adopt it when present, or create
it when absent; then reconcile its mutable fields (``minimum`` and ``maximum``).

The operator identifies a range by the resource's own fields, not by an
ownership marker stamped into it. A range is matched on its user-facing
``name`` (scoped by project when the spec is unshared), so ``spec.name`` is the
real Neutron name -- the operator neither prefixes it nor otherwise mangles it.
A range created out-of-band with the same name is adopted and converged rather
than duplicated.

A segment range outlives any single CR: it is shared infrastructure other
resources bind to, so the operator only ever finds, adopts, or creates one and
never deletes it. Deleting a CR leaves its range in place for an operator to
drain and remove.

Neutron's NetworkSegmentRange API only accepts ``name``, ``minimum`` and
``maximum`` on a PUT (see ``allow_put`` in
``neutron_lib/api/definitions/network_segment_range.py``); ``network_type``,
``physical_network``, ``shared`` and ``project_id`` are all immutable, so a
mismatch on any of them fails the CR loudly rather than silently diverging or
sending a PUT Neutron rejects with a bare 400.
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

#: Segment ranges already fetched this run, keyed by Neutron name.
RangeCache = dict[str, Any]


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


def find_range(conn: Any, spec: dict[str, Any], cache: RangeCache) -> Any | None:
    """Return the range the spec names, adopting one created out-of-band.

    Matching is by ``name`` -- the range's own user-facing identity. An
    unshared spec also scopes the match by ``project_id`` so two projects can
    hold same-named ranges without colliding. More than one match is ambiguous
    and raises rather than guessing which range to converge.

    The *cache* is populated once per credential group and shared across the
    group's CRs so each reconcile reuses one listing of Neutron.
    """
    name = str(spec["name"])
    if name in cache:
        return cache[name]

    query: dict[str, Any] = {"name": name}
    if not spec.get("shared", True) and spec.get("project_id"):
        query["project_id"] = spec["project_id"]

    matches = [
        segment_range
        for segment_range in conn.network.network_segment_ranges(**query)
        if str(get_value(segment_range, "name", default="")) == name
    ]
    if len(matches) > 1:
        raise ConfigError(
            f"Segment range name {name!r} matched {len(matches)} ranges; "
            "set spec.project_id to disambiguate"
        )
    match = matches[0] if matches else None
    if match is not None:
        cache[name] = match
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
        cache[name] = created
        LOG.info(
            "Reconciled segment range: %s",
            json.dumps(render_range(created), sort_keys=True),
        )
        return []

    LOG.info("Reusing segment range %s (%s)", name, resource_id(existing))

    drift = _immutable_drift(existing, spec)
    if drift:
        raise ConfigError(
            f"Segment range {name!r} already exists in Neutron with a different "
            f"immutable field ({drift}). Neutron only allows updating minimum "
            f"and maximum on an existing range; network_type, physical_network, "
            f"shared and project_id are fixed at creation. Rename the CR or "
            f"delete the existing range to let the operator recreate it."
        )

    updates = _mutable_updates(existing, spec)
    if not updates:
        LOG.info("Segment range %s already matches the spec", name)
        return []

    LOG.info("Reconciling segment range %s drift: %s", name, sorted(updates))
    updated = conn.network.update_network_segment_range(
        resource_id(existing), **updates
    )
    cache[name] = updated
    LOG.info(
        "Reconciled segment range: %s",
        json.dumps(render_range(updated), sort_keys=True),
    )
    return []
