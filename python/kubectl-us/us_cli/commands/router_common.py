"""Shared constants and helpers for router inspection commands."""

NEUTRON_PREFIX = "neutron-"
GATEWAY_DEVICE_OWNER = "network:router_gateway"
INTERFACE_DEVICE_OWNER = "network:router_interface"
ROUTER_INTERFACE_DEVICE_OWNERS = frozenset(
    {
        INTERFACE_DEVICE_OWNER,
        "network:router_interface_distributed",
        "network:ha_router_replicated_interface",
        "network:router_ha_interface",
    }
)


def rows_by_uuid(rows: list[dict], uuids: set[str]) -> list[dict]:
    """Return OVN rows referenced by a set of UUIDs."""
    return [row for row in rows if row.get("_uuid") in uuids]
