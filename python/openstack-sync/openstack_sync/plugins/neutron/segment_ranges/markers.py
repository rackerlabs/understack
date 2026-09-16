"""Ownership tracking for operator-managed network segment ranges.

A NeutronSegmentRange CR is an ownership claim for the matching OpenStack
segment range. Unlike Neutron flavors and service profiles, a segment range has
no ``description`` or ``meta_info`` field the operator can stamp -- Neutron's
NetworkSegmentRange resource exposes only ``name``, ``network_type``,
``physical_network``, ``minimum``, ``maximum``, ``shared`` and ``project_id``.

Ownership therefore rides on the range's ``name``. Every range the operator
creates or adopts carries an owner-prefixed name, and prune only ever deletes
ranges whose name carries that prefix. A range created out-of-band with a plain
name is never in the managed set, so it is never pruned.

The prefix is transparent to CR authors: ``spec.name`` is the logical name, and
:func:`managed_name` / :func:`logical_name` translate between the logical name
and the name stored in Neutron.
"""

from __future__ import annotations

from typing import Any

from openstack_sync.plugins.common import get_value

#: Prepended to every operator-managed segment range name in Neutron. Chosen to
#: be unambiguous and to survive Neutron's name length limit (255) with room to
#: spare for a logical name.
NAME_PREFIX = "understack-sr:"


def managed_name(logical_name: str) -> str:
    """Return the Neutron range name for a CR's logical *logical_name*."""
    if logical_name.startswith(NAME_PREFIX):
        return logical_name
    return f"{NAME_PREFIX}{logical_name}"


def logical_name(neutron_name: str) -> str:
    """Return the CR-facing logical name for a Neutron range *neutron_name*."""
    if neutron_name.startswith(NAME_PREFIX):
        return neutron_name[len(NAME_PREFIX) :]
    return neutron_name


def is_managed_range(segment_range: Any) -> bool:
    """Return True when *segment_range*'s name carries the operator prefix."""
    name = str(get_value(segment_range, "name", default=""))
    return name.startswith(NAME_PREFIX)
