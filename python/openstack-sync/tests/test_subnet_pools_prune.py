"""Tests for subnet pool prune behaviour."""

from __future__ import annotations

import types
from typing import Any

from openstack_sync.plugins.neutron.subnet_pools import prune
from openstack_sync.plugins.neutron.subnet_pools.config import OWNERSHIP_TAG


class FakeNetwork:
    def __init__(self, pools: list[Any]):
        self._pools = pools
        self.deleted: list[str] = []

    def subnet_pools(self) -> list[Any]:
        return list(self._pools)

    def delete_subnet_pool(self, pool: Any, ignore_missing: bool = True) -> None:
        self.deleted.append(pool.id)
        self._pools = [item for item in self._pools if item.id != pool.id]


def _pool(name: str, *, managed: bool = True) -> Any:
    tags = [OWNERSHIP_TAG] if managed else []
    return types.SimpleNamespace(id=f"{name}-id", name=name, tags=tags)


def _conn(pools: list[Any]) -> Any:
    return types.SimpleNamespace(network=FakeNetwork(pools))


def test_prune_deletes_removed_owned_subnet_pool():
    conn = _conn([_pool("removed-pool"), _pool("kept-pool")])

    prune.prune_removed_subnet_pools(conn, ["kept-pool"])

    assert conn.network.deleted == ["removed-pool-id"]


def test_prune_keeps_unowned_subnet_pool():
    conn = _conn([_pool("manual-pool", managed=False)])

    prune.prune_removed_subnet_pools(conn, ["kept-pool"])

    assert conn.network.deleted == []


def test_prune_keeps_owned_pools_when_desired_list_is_empty():
    conn = _conn([_pool("managed-pool")])

    prune.prune_removed_subnet_pools(conn, [])

    assert conn.network.deleted == []


def test_prune_deletes_when_empty_desired_is_authoritative():
    conn = _conn([_pool("managed-pool")])

    prune.prune_removed_subnet_pools(conn, [], authoritative_empty=True)

    assert conn.network.deleted == ["managed-pool-id"]
