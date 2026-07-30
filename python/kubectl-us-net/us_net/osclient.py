"""OpenStack SDK connection + router resolution helpers."""

from __future__ import annotations

import openstack
from openstack.connection import Connection


def get_connection(os_cloud: str | None) -> Connection:
    """Connect to OpenStack, falling back to OS_CLOUD/clouds.yaml when unset."""
    return openstack.connect(cloud=os_cloud)


def describe_target(os_cloud: str | None) -> list[tuple[str, str]]:
    """(label, value) pairs describing the OpenStack target; never includes secrets."""
    try:
        conn = get_connection(os_cloud)
    except Exception as exc:
        return [("status", f"unavailable ({exc})")]
    config = conn.config.config
    auth = config.get("auth", {})
    pairs = [
        (label, value)
        for label, value in (
            ("auth URL", auth.get("auth_url")),
            ("region", config.get("region_name")),
            ("project", auth.get("project_name")),
            ("username", auth.get("username")),
        )
        if value
    ]
    return pairs or [("status", "(no auth details in configuration)")]


def resolve_router(conn: Connection, name_or_id: str):
    """Resolve a Neutron router by name or ID, raising LookupError if not found."""
    router = conn.network.find_router(name_or_id)
    if router is None:
        raise LookupError(f"router {name_or_id!r} not found")
    return router
