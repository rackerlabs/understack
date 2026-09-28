"""Reconcile a NeutronSegmentRange CR onto Neutron.

Find the operator-managed range by its owner-prefixed name; create it when
absent, or reconcile its mutable fields (``minimum`` and ``maximum``) when
present. Neutron's NetworkSegmentRange API only accepts ``name``, ``minimum``
and ``maximum`` on a PUT (see ``allow_put`` in
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
from openstack_sync.plugins.neutron.segment_ranges.markers import logical_name
from openstack_sync.plugins.neutron.segment_ranges.markers import managed_name

LOG = logging.getLogger(__name__)

#: Segment ranges already fetched this run, keyed by managed (Neutron) name.
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


def load_managed_ranges(conn: Any, cache: RangeCache) -> RangeCache:
    """Populate *cache* with every operator-managed range, keyed by name.

    Only ranges whose name already carries the operator prefix are cached, so
    this finds ranges the operator itself created; a range created out-of-band
    with a plain name is not adopted. Fetched once per credential group and
    shared across the group's CRs so each reconcile reuses one listing.
    """
    if cache:
        return cache
    for segment_range in conn.network.network_segment_ranges():
        name = str(get_value(segment_range, "name", default=""))
        if name.startswith(managed_name("")):
            cache[name] = segment_range
    return cache


def find_range(conn: Any, managed: str, cache: RangeCache) -> Any | None:
    """Return the operator-managed range named *managed*, or None."""
    load_managed_ranges(conn, cache)
    return cache.get(managed)


def _immutable_drift(segment_range: Any, spec: dict[str, Any]) -> str | None:
    """Return a description of any immutable-field mismatch, else None.

    Neutron accepts only ``name``, ``minimum`` and ``maximum`` on a PUT, so
    ``network_type``, ``physical_network``, ``shared`` and ``project_id`` are
    all immutable: a CR that changes any of them must fail loudly here rather
    than send a PUT Neutron rejects with a bare 400.

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


def _create_kwargs(managed: str, spec: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "name": managed,
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
    """Return the reconciled range as a loggable dict, with the logical name."""
    return {
        "id": get_value(segment_range, "id"),
        "name": logical_name(str(get_value(segment_range, "name", default=""))),
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
    managed = managed_name(name)
    existing = find_range(conn, managed, cache)

    if existing is None:
        LOG.info(
            "Creating segment range %s type=%s physical=%s %s-%s",
            name,
            spec["network_type"],
            spec.get("physical_network"),
            spec["minimum"],
            spec["maximum"],
        )
        created = conn.network.create_network_segment_range(
            **_create_kwargs(managed, spec)
        )
        cache[managed] = created
        LOG.info(
            "Reconciled segment range: %s",
            json.dumps(render_range(created), sort_keys=True),
        )
        return []

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
    cache[managed] = updated
    LOG.info(
        "Reconciled segment range: %s",
        json.dumps(render_range(updated), sort_keys=True),
    )
    return []
