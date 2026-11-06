"""Ownership helpers for operator-managed Neutron subnet pools."""

from __future__ import annotations

from typing import Any

from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.neutron.subnet_pools.config import OWNERSHIP_TAG


def subnet_pool_tags(pool: Any) -> list[str]:
    return [str(tag) for tag in get_value(pool, "tags", default=[]) or []]


def is_managed_subnet_pool(pool: Any) -> bool:
    return OWNERSHIP_TAG in subnet_pool_tags(pool)


def desired_tags(spec: dict[str, Any]) -> list[str]:
    """Return the CR's ``spec.tags`` plus the ownership marker."""
    tags = {str(tag) for tag in spec.get("tags", [])}
    tags.add(OWNERSHIP_TAG)
    return sorted(tags)
