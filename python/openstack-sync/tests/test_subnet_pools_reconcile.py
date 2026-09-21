"""Tests for Neutron subnet pool reconciliation.

Nautobot resolution is stubbed here so these tests exercise only the Neutron
convergence path; ``test_subnet_pools_nautobot.py`` covers resolution itself.
"""

from __future__ import annotations

import types
from typing import Any
from unittest import mock

import pytest

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.neutron.subnet_pools import reconcile
from openstack_sync.plugins.neutron.subnet_pools.config import OWNERSHIP_TAG


def _scope(
    scope_id: str = "scope-id",
    name: str = "scope-a",
    ip_version: int = 4,
) -> Any:
    return types.SimpleNamespace(id=scope_id, name=name, ip_version=ip_version)


def _pool(
    pool_id: str = "pool-id",
    name: str = "pool-a",
    address_scope_id: str = "scope-id",
    prefixes: list[str] | None = None,
    tags: list[str] | None = None,
) -> Any:
    return types.SimpleNamespace(
        id=pool_id,
        name=name,
        address_scope_id=address_scope_id,
        project_id="project-a",
        prefixes=prefixes or ["10.0.0.0/8"],
        ip_version=4,
        default_prefix_length=24,
        minimum_prefix_length=24,
        maximum_prefix_length=28,
        description="pool desc",
        is_default=False,
        is_shared=False,
        tags=tags if tags is not None else [OWNERSHIP_TAG],
    )


def _spec(**overrides: Any) -> dict[str, Any]:
    """A spec already carrying what nautobot.resolve_spec attaches.

    ``prefixes``/``ip_version``/``nautobot_prefix_links`` are exactly the
    fields the real resolver adds; ``_stub_nautobot`` below bypasses the
    resolver itself but keeps its output contract.
    """
    spec: dict[str, Any] = {
        "name": "pool-a",
        "project_id": "project-a",
        "address_scope": {"name": "scope-a"},
        "prefixes": ["10.0.0.0/8"],
        "ip_version": 4,
        "nautobot_prefix_links": [
            {
                "id": "2bc3ecab-b6dc-46cd-9bd4-1c0ea8a07f87",
                "cidr": "10.0.0.0/8",
                "url": "https://nautobot.example.test/ipam/prefixes/"
                "2bc3ecab-b6dc-46cd-9bd4-1c0ea8a07f87/",
            }
        ],
        "default_prefix_length": 24,
        "minimum_prefix_length": 24,
        "maximum_prefix_length": 28,
        "shared": False,
        "description": "pool desc",
        "tags": ["tenant"],
    }
    spec.update(overrides)
    return spec


def _conn(network: Any) -> Any:
    return types.SimpleNamespace(network=network)


@pytest.fixture(autouse=True)
def _stub_nautobot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bypass Nautobot: return the given spec unchanged (it already resolves)."""
    monkeypatch.setattr(
        reconcile.nautobot_module,
        "resolve_spec",
        lambda spec, cache, namespace: spec,
    )


def test_sync_subnet_pool_creates_with_resolved_address_scope_and_tags():
    network = mock.MagicMock()
    network.address_scopes.return_value = [_scope()]
    network.subnet_pools.return_value = []
    created = _pool(tags=[])
    network.create_subnet_pool.return_value = created
    conn = _conn(network)

    reconcile.sync_subnet_pool(conn, _spec(), "openstack", {})

    create_kwargs = network.create_subnet_pool.call_args.kwargs
    assert create_kwargs["address_scope_id"] == "scope-id"
    assert create_kwargs["default_prefix_length"] == 24
    assert create_kwargs["minimum_prefix_length"] == 24
    assert create_kwargs["maximum_prefix_length"] == 28
    assert create_kwargs["is_shared"] is False
    assert "ip_version" not in create_kwargs
    network.set_tags.assert_called_once_with(created, ["tenant", OWNERSHIP_TAG])


def test_sync_subnet_pool_creates_without_address_scope_when_absent():
    network = mock.MagicMock()
    network.subnet_pools.return_value = []
    created = _pool(tags=[], address_scope_id=None)
    network.create_subnet_pool.return_value = created
    conn = _conn(network)

    reconcile.sync_subnet_pool(conn, _spec(address_scope=None), "openstack", {})

    create_kwargs = network.create_subnet_pool.call_args.kwargs
    assert "address_scope_id" not in create_kwargs
    network.address_scopes.assert_not_called()


def test_sync_subnet_pool_updates_mutable_drift():
    existing = _pool(
        address_scope_id="old-scope",
        prefixes=["10.1.0.0/16"],
        tags=[OWNERSHIP_TAG],
    )
    updated = _pool(tags=[OWNERSHIP_TAG, "tenant"])
    network = mock.MagicMock()
    network.address_scopes.return_value = [_scope()]
    network.subnet_pools.return_value = [existing]
    network.update_subnet_pool.return_value = updated
    conn = _conn(network)

    reconcile.sync_subnet_pool(conn, _spec(), "openstack", {})

    update_kwargs = network.update_subnet_pool.call_args.kwargs
    assert update_kwargs["address_scope_id"] == "scope-id"
    assert update_kwargs["prefixes"] == ["10.0.0.0/8"]
    network.set_tags.assert_not_called()


def test_sync_adopts_ansible_created_pool_without_shrinking():
    """Adopt a pool the retired Ansible role created.

    Such a pool is untagged, has no address scope, and is shared. Adoption must
    stamp the ownership tag and add the address scope without treating the
    existing prefixes as a shrink.
    """
    existing = _pool(
        address_scope_id=None,
        prefixes=["10.0.0.0/8"],
        tags=[],
    )
    existing.is_shared = True
    updated = _pool(tags=[OWNERSHIP_TAG])
    network = mock.MagicMock()
    network.address_scopes.return_value = [_scope()]
    network.subnet_pools.return_value = [existing]
    network.update_subnet_pool.return_value = updated
    conn = _conn(network)

    result = reconcile.sync_subnet_pool(conn, _spec(shared=True), "openstack", {})

    assert result.notes == []
    update_kwargs = network.update_subnet_pool.call_args.kwargs
    assert update_kwargs["address_scope_id"] == "scope-id"
    assert "prefixes" not in update_kwargs  # unchanged, so not pushed
    network.set_tags.assert_called_once_with(updated, ["tenant", OWNERSHIP_TAG])


def test_sync_reports_note_and_keeps_prefixes_when_pool_would_shrink():
    """Report a note instead of failing when a pool would shrink.

    Removing a prefix reference cannot be reconciled: Neutron forbids shrinking
    a pool. The reconcile keeps the prefixes and reports a note.
    """
    existing = _pool(
        prefixes=["10.0.0.0/8", "192.0.2.0/24"],
        tags=[OWNERSHIP_TAG],
    )
    network = mock.MagicMock()
    network.address_scopes.return_value = [_scope()]
    network.subnet_pools.return_value = [existing]
    network.update_subnet_pool.return_value = existing
    conn = _conn(network)

    # Spec now only wants 10.0.0.0/8, dropping 192.0.2.0/24.
    result = reconcile.sync_subnet_pool(conn, _spec(prefixes=["10.0.0.0/8"]), "ns", {})

    assert len(result.notes) == 1
    assert "192.0.2.0/24" in result.notes[0]
    if network.update_subnet_pool.called:
        assert "prefixes" not in network.update_subnet_pool.call_args.kwargs


def test_sync_subnet_pool_reports_resolved_prefix_links():
    """nautobot_prefix_links on the resolved spec is surfaced verbatim."""
    links = [
        {
            "id": "2bc3ecab-b6dc-46cd-9bd4-1c0ea8a07f87",
            "cidr": "10.0.0.0/8",
            "url": "https://nautobot.example.test/ipam/prefixes/"
            "2bc3ecab-b6dc-46cd-9bd4-1c0ea8a07f87/",
        }
    ]
    network = mock.MagicMock()
    network.address_scopes.return_value = [_scope()]
    network.subnet_pools.return_value = []
    network.create_subnet_pool.return_value = _pool(tags=[])
    conn = _conn(network)

    result = reconcile.sync_subnet_pool(
        conn, _spec(nautobot_prefix_links=links), "openstack", {}
    )

    assert result.extra_status == {"prefixes": links}


def test_ensure_address_scope_by_id_uses_exact_lookup():
    network = mock.MagicMock()
    network.get_address_scope.return_value = _scope(scope_id="scope-by-id")
    conn = _conn(network)

    scope = reconcile.ensure_address_scope(
        conn,
        _spec(address_scope={"id": "scope-by-id"}),
        4,
    )

    assert scope.id == "scope-by-id"
    network.get_address_scope.assert_called_once_with("scope-by-id")
    network.address_scopes.assert_not_called()
    network.create_address_scope.assert_not_called()


def test_ensure_address_scope_returns_none_when_absent():
    network = mock.MagicMock()
    conn = _conn(network)

    assert reconcile.ensure_address_scope(conn, _spec(address_scope=None), 4) is None
    network.get_address_scope.assert_not_called()
    network.address_scopes.assert_not_called()
    network.create_address_scope.assert_not_called()


def test_ensure_address_scope_rejects_ambiguous_name():
    network = mock.MagicMock()
    network.address_scopes.return_value = [
        _scope(scope_id="scope-a"),
        _scope(scope_id="scope-b"),
    ]
    conn = _conn(network)

    with pytest.raises(ConfigError, match="matched 2 scopes"):
        reconcile.ensure_address_scope(conn, _spec(), 4)


def test_ensure_address_scope_adopts_existing_named_scope():
    """A scope that already exists is reused, never recreated."""
    network = mock.MagicMock()
    network.address_scopes.return_value = [_scope(scope_id="existing")]
    conn = _conn(network)

    scope = reconcile.ensure_address_scope(conn, _spec(), 4)

    assert scope.id == "existing"
    network.create_address_scope.assert_not_called()


def test_ensure_address_scope_creates_named_scope_when_absent():
    """A greenfield pool creates its address scope, shared, in the pool family."""
    network = mock.MagicMock()
    network.address_scopes.return_value = []
    network.create_address_scope.return_value = _scope(scope_id="created")
    conn = _conn(network)

    scope = reconcile.ensure_address_scope(
        conn, _spec(address_scope={"name": "scope-a", "shared": True}), 4
    )

    assert scope.id == "created"
    create_kwargs = network.create_address_scope.call_args.kwargs
    assert create_kwargs["name"] == "scope-a"
    assert create_kwargs["ip_version"] == 4
    assert create_kwargs["is_shared"] is True


def test_ensure_address_scope_creates_scope_in_pool_ip_family():
    """The created scope's ip_version follows the pool, not a fixed default."""
    network = mock.MagicMock()
    network.address_scopes.return_value = []
    network.create_address_scope.return_value = _scope(
        scope_id="created6", ip_version=6
    )
    conn = _conn(network)

    reconcile.ensure_address_scope(conn, _spec(), 6)

    assert network.create_address_scope.call_args.kwargs["ip_version"] == 6


def test_ensure_address_scope_create_false_requires_existing_scope():
    """create: false resolves only, failing when the scope is absent."""
    network = mock.MagicMock()
    network.address_scopes.return_value = []
    conn = _conn(network)

    with pytest.raises(ConfigError, match="create is false"):
        reconcile.ensure_address_scope(
            conn, _spec(address_scope={"name": "scope-a", "create": False}), 4
        )
    network.create_address_scope.assert_not_called()


def test_sync_subnet_pool_creates_address_scope_then_links_it():
    """End to end: a missing scope is created and its id lands on the pool."""
    network = mock.MagicMock()
    network.address_scopes.return_value = []
    network.create_address_scope.return_value = _scope(scope_id="new-scope")
    network.subnet_pools.return_value = []
    network.create_subnet_pool.return_value = _pool(tags=[])
    conn = _conn(network)

    reconcile.sync_subnet_pool(conn, _spec(), "openstack", {})

    network.create_address_scope.assert_called_once()
    assert (
        network.create_subnet_pool.call_args.kwargs["address_scope_id"] == "new-scope"
    )


def test_validate_prefixes_rejects_mixed_families():
    with pytest.raises(ConfigError, match="same IP version"):
        reconcile.validate_prefixes(_spec(prefixes=["10.0.0.0/8", "fd00::/48"]))


def test_validate_prefixes_rejects_length_exceeding_family_max():
    with pytest.raises(ConfigError, match="maximum prefix length 32"):
        reconcile.validate_prefixes(_spec(maximum_prefix_length=64))


def test_validate_prefixes_requires_all_prefix_lengths():
    """Reject a pool with no prefix lengths.

    Rather than leave it to Neutron's permissive defaults, the operator
    requires all three bounds.
    """
    spec = _spec()
    del spec["default_prefix_length"]
    del spec["minimum_prefix_length"]
    del spec["maximum_prefix_length"]
    with pytest.raises(ConfigError, match="missing prefix length"):
        reconcile.validate_prefixes(spec)


def test_validate_prefixes_rejects_min_greater_than_max():
    with pytest.raises(ConfigError, match="minimum_prefix_length must be less"):
        reconcile.validate_prefixes(
            _spec(minimum_prefix_length=28, maximum_prefix_length=24)
        )


# ---------------------------------------------------------------------------
# is_default single-per-family guard
# ---------------------------------------------------------------------------


def _routing_network(*, by_name: list[Any], default_holders: list[Any]) -> Any:
    """A network mock that answers subnet_pools() by query kind.

    find_subnet_pool queries by name; the default-conflict check queries by
    is_default + ip_version. Route each to its own list so one call does not
    leak into the other.
    """
    network = mock.MagicMock()
    network.address_scopes.return_value = [_scope()]

    def subnet_pools(**kwargs: Any) -> list[Any]:
        if kwargs.get("is_default"):
            return list(default_holders)
        return list(by_name)

    network.subnet_pools.side_effect = subnet_pools
    return network


def test_sync_rejects_second_default_for_same_family():
    """A CR asking to be default when another pool already is fails clearly."""
    other_default = _pool(pool_id="other-id", name="other-default")
    other_default.is_default = True
    network = _routing_network(by_name=[], default_holders=[other_default])
    network.create_subnet_pool.return_value = _pool(tags=[])
    conn = _conn(network)

    with pytest.raises(ConfigError, match="already the default for that family"):
        reconcile.sync_subnet_pool(conn, _spec(is_default=True), "openstack", {})

    network.create_subnet_pool.assert_not_called()


def test_sync_allows_default_when_no_other_default_exists():
    network = _routing_network(by_name=[], default_holders=[])
    created = _pool(tags=[])
    network.create_subnet_pool.return_value = created
    conn = _conn(network)

    reconcile.sync_subnet_pool(conn, _spec(is_default=True), "openstack", {})

    assert network.create_subnet_pool.call_args.kwargs["is_default"] is True


def test_sync_default_does_not_conflict_with_itself():
    """The pool this CR already manages is exempt from the default check."""
    existing = _pool(prefixes=["10.0.0.0/8"], tags=[OWNERSHIP_TAG])
    existing.is_default = True
    network = _routing_network(by_name=[existing], default_holders=[existing])
    network.update_subnet_pool.return_value = existing
    conn = _conn(network)

    # Must not raise: the only default holder is the pool we manage.
    reconcile.sync_subnet_pool(conn, _spec(is_default=True), "openstack", {})


def test_sync_skips_default_check_when_not_default():
    """is_default=false must not query for existing defaults at all."""
    network = _routing_network(by_name=[], default_holders=[_pool()])
    network.create_subnet_pool.return_value = _pool(tags=[])
    conn = _conn(network)

    reconcile.sync_subnet_pool(conn, _spec(), "openstack", {})

    for call in network.subnet_pools.call_args_list:
        assert not call.kwargs.get("is_default")
