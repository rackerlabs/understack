"""Reconcile a NeutronSubnetPool CR onto Neutron.

Resolve the CR's Nautobot prefix references into CIDRs and an IP version,
validate them, ensure the address scope (create if absent, adopt if present),
then converge the subnet pool and link the scope. Nautobot stays the source of
truth for CIDRs; ``nautobot.py`` hands this module a spec already carrying
``prefixes`` and ``ip_version``.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from typing import Any

from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.neutron.subnet_pools import nautobot as nautobot_module
from openstack_sync.plugins.neutron.subnet_pools.markers import desired_tags

LOG = logging.getLogger(__name__)


def _prefix_networks(
    prefixes: list[str],
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    try:
        return [ipaddress.ip_network(prefix) for prefix in prefixes]
    except ValueError as exc:
        raise ConfigError(f"Invalid subnet pool prefix: {exc}") from exc


#: All three prefix-length bounds are required. Neutron would otherwise fill in
#: permissive defaults for any that are missing, giving an over-broad pool.
REQUIRED_PREFIX_LENGTHS = (
    "minimum_prefix_length",
    "default_prefix_length",
    "maximum_prefix_length",
)


def validate_prefixes(spec: dict[str, Any]) -> int:
    """Validate CIDR prefixes and prefix-length bounds; return the IP version.

    Enforces the parts of the Neutron subnet-pool contract the OpenAPI schema
    cannot: the CIDR set (resolved from Nautobot) is non-empty and single-family
    and matches spec.ip_version, and the three prefix-length bounds are within
    the IP family and ordered minimum <= default <= maximum.
    """
    missing = [name for name in REQUIRED_PREFIX_LENGTHS if spec.get(name) is None]
    if missing:
        raise ConfigError(
            f"Subnet pool {spec.get('name')!r} is missing prefix length(s) "
            f"{missing}: set minimum_prefix_length, default_prefix_length, and "
            "maximum_prefix_length on the CR spec"
        )

    prefixes = spec["prefixes"]
    networks = _prefix_networks(prefixes)
    versions = {network.version for network in networks}
    if len(versions) != 1:
        raise ConfigError("All subnet pool prefixes must have the same IP version")

    (version,) = versions
    requested_version = spec.get("ip_version")
    if requested_version is not None and requested_version != version:
        raise ConfigError(
            f"Subnet pool {spec['name']!r} prefixes are IPv{version}, "
            f"but spec.ip_version is {requested_version}"
        )

    family_max = 32 if version == 4 else 128
    length_names = (
        "default_prefix_length",
        "minimum_prefix_length",
        "maximum_prefix_length",
    )
    for name in length_names:
        length = spec.get(name)
        if length is not None and int(length) > family_max:
            raise ConfigError(
                f"Subnet pool {spec['name']!r} {name}={length} exceeds "
                f"IPv{version} maximum prefix length {family_max}"
            )

    min_len = spec.get("minimum_prefix_length")
    default_len = spec.get("default_prefix_length")
    max_len = spec.get("maximum_prefix_length")
    if (
        min_len is not None
        and default_len is not None
        and int(min_len) > int(default_len)
    ):
        raise ConfigError(
            "minimum_prefix_length must be less than or equal to default_prefix_length"
        )
    if (
        default_len is not None
        and max_len is not None
        and int(default_len) > int(max_len)
    ):
        raise ConfigError(
            "default_prefix_length must be less than or equal to maximum_prefix_length"
        )
    if min_len is not None and max_len is not None and int(min_len) > int(max_len):
        raise ConfigError(
            "minimum_prefix_length must be less than or equal to maximum_prefix_length"
        )

    return version


def _get_address_scope(conn: Any, scope_id: str) -> Any:
    try:
        return conn.network.get_address_scope(scope_id)
    except openstack_exceptions.NotFoundException as exc:
        raise ConfigError(f"Address scope {scope_id!r} was not found") from exc


def _scope_project_query(
    spec: dict[str, Any], scope_spec: dict[str, Any]
) -> str | None:
    return scope_spec.get("project_id") or spec.get("project_id")


def _find_address_scope_by_name(
    conn: Any, scope_name: str, ip_version: int, project_id: str | None
) -> Any | None:
    """Return the single scope matching *scope_name* and *ip_version*, or None.

    More than one match in the same IP family is ambiguous and raises.
    """
    query: dict[str, Any] = {"name": scope_name, "ip_version": ip_version}
    if project_id:
        query["project_id"] = project_id
    scopes = [
        scope
        for scope in conn.network.address_scopes(**query)
        if get_value(scope, "name") == scope_name
    ]
    if len(scopes) > 1:
        raise ConfigError(
            f"Address scope name {scope_name!r} matched {len(scopes)} "
            "scopes; set spec.address_scope.id or project_id"
        )
    return scopes[0] if scopes else None


def _create_address_scope(
    conn: Any,
    scope_name: str,
    ip_version: int,
    scope_spec: dict[str, Any],
    project_id: str | None,
) -> Any:
    # ip_version follows the pool's prefixes; shared defaults true like the pools.
    attrs: dict[str, Any] = {
        "name": scope_name,
        "ip_version": ip_version,
        "is_shared": bool(scope_spec.get("shared", True)),
    }
    if project_id:
        attrs["project_id"] = project_id
    LOG.info(
        "Creating address scope %s ip_version=%s shared=%s",
        scope_name,
        ip_version,
        attrs["is_shared"],
    )
    return conn.network.create_address_scope(**attrs)


def ensure_address_scope(
    conn: Any, spec: dict[str, Any], ip_version: int
) -> Any | None:
    """Find, adopt, or create the address scope a CR spec declares.

    A scope named by the spec is reused when present and created when absent
    (unless create is false); a scope referenced by id must already exist. The
    operator never deletes an address scope: it outlives any single pool and the
    L3/SVI validation of every subnet under it depends on it surviving.

    Returns None only when the spec declares no address scope (the CRD requires
    it, so this is a defensive fallback).
    """
    scope_spec = spec.get("address_scope")
    if not scope_spec:
        return None

    if scope_id := scope_spec.get("id"):
        scope = _get_address_scope(conn, str(scope_id))
    else:
        scope_name = str(scope_spec["name"])
        project_id = _scope_project_query(spec, scope_spec)
        scope = _find_address_scope_by_name(conn, scope_name, ip_version, project_id)
        if scope is not None:
            LOG.info(
                "Reusing address scope %s (%s) for subnet pool %s",
                scope_name,
                resource_id(scope),
                spec["name"],
            )
        elif scope_spec.get("create", True):
            scope = _create_address_scope(
                conn, scope_name, ip_version, scope_spec, project_id
            )
        else:
            raise ConfigError(
                f"Address scope {scope_name!r} was not found for IPv{ip_version} "
                "and spec.address_scope.create is false"
            )

    scope_version = get_value(scope, "ip_version")
    if scope_version is not None and int(scope_version) != ip_version:
        raise ConfigError(
            f"Address scope {resource_id(scope)!r} is IPv{scope_version}, "
            f"but subnet pool {spec['name']!r} is IPv{ip_version}"
        )
    return scope


def _normalized_prefixes(prefixes: list[str]) -> list[str]:
    return sorted(str(network) for network in _prefix_networks(prefixes))


def _network_is_covered(
    network: ipaddress.IPv4Network | ipaddress.IPv6Network,
    covering: list[ipaddress.IPv4Network | ipaddress.IPv6Network],
) -> bool:
    """Return whether *network* falls entirely within one of *covering*."""
    return any(
        network.version == other.version
        and int(network.network_address) >= int(other.network_address)
        and int(network.broadcast_address) <= int(other.broadcast_address)
        for other in covering
    )


def _prefixes_removed(have: list[str], want: list[str]) -> list[str]:
    """Return CIDRs in *have* that the *want* set no longer covers.

    Neutron forbids shrinking a subnet pool: on update the existing prefix set
    must be a subset of the new one, or it raises IllegalSubnetPoolPrefixUpdate
    (HTTP 409). Removing a Nautobot prefix reference from a CR therefore cannot
    be reconciled by the operator; draining and deleting the pool is an operator
    decision. Detecting it here lets the reconcile report the drift as a note
    and stay Synced rather than failing every cycle on a 409 it cannot resolve.
    """
    want_networks = _prefix_networks(want)
    return sorted(
        str(network)
        for network in _prefix_networks(have)
        if not _network_is_covered(network, want_networks)
    )


def _subnet_pool_values(pool: Any) -> dict[str, Any]:
    return {
        "address_scope_id": get_value(pool, "address_scope_id"),
        "description": get_value(pool, "description", default=""),
        "prefixes": get_value(pool, "prefixes", default=[]),
        "default_prefix_length": get_value(pool, "default_prefix_length"),
        "minimum_prefix_length": get_value(pool, "minimum_prefix_length"),
        "maximum_prefix_length": get_value(pool, "maximum_prefix_length"),
        "is_default": get_value(pool, "is_default", default=False),
    }


def _desired_attrs(
    spec: dict[str, Any], address_scope_id: str | None
) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "name": spec["name"],
        "prefixes": spec["prefixes"],
        "description": spec.get("description", ""),
        "is_default": bool(spec.get("is_default", False)),
    }
    if address_scope_id is not None:
        attrs["address_scope_id"] = address_scope_id
    optional_fields = {
        "project_id": "project_id",
        "shared": "is_shared",
        "default_prefix_length": "default_prefix_length",
        "minimum_prefix_length": "minimum_prefix_length",
        "maximum_prefix_length": "maximum_prefix_length",
    }
    for spec_name, attr_name in optional_fields.items():
        if spec_name in spec:
            attrs[attr_name] = spec[spec_name]
    return attrs


def _check_default_conflict(
    conn: Any, spec: dict[str, Any], ip_version: int, pool: Any | None
) -> None:
    """Fail early if another pool is already the default for this IP family.

    Neutron allows only one default subnet pool per IP family and returns a
    generic ``InvalidInput`` (HTTP 400) if a second is created. is_default is
    also admin-only. Detecting the conflict here turns that opaque error into a
    message naming the pool that already holds the default, and avoids a CR that
    would fail every reconcile cycle. *pool* is the existing pool this CR
    manages, if any; a pool that is already the default does not conflict with
    itself.
    """
    if not bool(spec.get("is_default", False)):
        return
    pool_id = resource_id(pool) if pool else None
    existing = [
        other
        for other in conn.network.subnet_pools(is_default=True, ip_version=ip_version)
        if bool(get_value(other, "is_default", default=False))
        and int(get_value(other, "ip_version") or ip_version) == ip_version
        and resource_id(other) != pool_id
    ]
    if existing:
        holder = existing[0]
        raise ConfigError(
            f"Subnet pool {spec['name']!r} requests is_default=true for IPv"
            f"{ip_version}, but pool {get_value(holder, 'name')!r} "
            f"({resource_id(holder)}) is already the default for that family. "
            "Neutron allows only one default subnet pool per IP family; clear "
            "is_default on the other pool or on this CR."
        )


def find_subnet_pool(conn: Any, spec: dict[str, Any]) -> Any | None:
    """Return the subnet pool matching the spec name and optional project."""
    query: dict[str, Any] = {"name": spec["name"]}
    if project_id := spec.get("project_id"):
        query["project_id"] = project_id
    matches = [
        pool
        for pool in conn.network.subnet_pools(**query)
        if get_value(pool, "name") == spec["name"]
    ]
    if len(matches) > 1:
        raise ConfigError(
            f"Subnet pool name {spec['name']!r} matched {len(matches)} pools; "
            "set spec.project_id"
        )
    return matches[0] if matches else None


def _update_attrs(pool: Any, desired: dict[str, Any]) -> dict[str, Any]:
    current = _subnet_pool_values(pool)
    updates: dict[str, Any] = {}
    for name, want in desired.items():
        if name in {"name", "project_id", "is_shared"}:
            continue
        have = current.get(name)
        if name == "prefixes":
            if _normalized_prefixes(list(have or [])) != _normalized_prefixes(
                list(want)
            ):
                updates[name] = want
            continue
        if have != want:
            updates[name] = want
    return updates


def _validate_existing(pool: Any, spec: dict[str, Any], ip_version: int) -> None:
    pool_id = resource_id(pool)
    if spec_project := spec.get("project_id"):
        pool_project = get_value(pool, "project_id")
        if pool_project and pool_project != spec_project:
            raise ConfigError(
                f"Subnet pool {spec['name']!r} ({pool_id}) belongs to "
                f"project_id={pool_project!r}; expected {spec_project!r}"
            )
    if "shared" in spec:
        current_shared = bool(get_value(pool, "is_shared", default=False))
        if current_shared != bool(spec["shared"]):
            raise ConfigError(
                f"Subnet pool {spec['name']!r} ({pool_id}) has shared="
                f"{current_shared}; Neutron does not allow updating shared on an "
                "existing subnet pool. Drain and delete the pool to let the "
                "operator recreate it, or set spec.shared to match."
            )
    pool_version = get_value(pool, "ip_version")
    if pool_version is not None and int(pool_version) != ip_version:
        raise ConfigError(
            f"Subnet pool {spec['name']!r} ({pool_id}) is IPv{pool_version}; "
            f"expected IPv{ip_version}"
        )


def _ensure_tags(conn: Any, pool: Any, spec: dict[str, Any]) -> None:
    current_tags = sorted(str(tag) for tag in get_value(pool, "tags", default=[]) or [])
    want_tags = desired_tags(spec)
    if current_tags == want_tags:
        return
    LOG.info("Reconciling subnet pool %s tags to %s", resource_id(pool), want_tags)
    conn.network.set_tags(pool, want_tags)


def render_subnet_pool(pool: Any) -> dict[str, Any]:
    return {
        "id": get_value(pool, "id"),
        "name": get_value(pool, "name"),
        "address_scope_id": get_value(pool, "address_scope_id"),
        "project_id": get_value(pool, "project_id"),
        "prefixes": get_value(pool, "prefixes", default=[]),
        "ip_version": get_value(pool, "ip_version"),
        "is_default": get_value(pool, "is_default"),
        "is_shared": get_value(pool, "is_shared"),
        "tags": get_value(pool, "tags", default=[]),
    }


def resolve_desired_names(specs: list[dict[str, Any]]) -> list[str]:
    """Return the Neutron pool name each CR spec manages.

    Prune matches Neutron pools by name. The name is declared directly on the
    CR (``spec.name`` is required), so prune needs no Nautobot call to learn it:
    it reads the literal name from each surviving spec. This keeps prune from
    depending on Nautobot reachability, so a Nautobot outage can never make a
    live CR's pool look undesired and turn it into a delete candidate.

    A spec missing a name is skipped with a warning; it also failed CRD
    validation and reconcile, so the run already reports failure and prune is
    skipped anyway.
    """
    names: list[str] = []
    for spec in specs:
        name = str(spec.get("name") or "").strip()
        if not name:
            LOG.warning("Skipping subnet pool spec with no name for prune")
            continue
        names.append(name)
    return names


def sync_subnet_pool(
    conn: Any, spec: dict[str, Any], namespace: str, cache: dict[str, Any]
) -> list[str]:
    """Converge one NeutronSubnetPool spec.

    Resolves the CR's Nautobot prefix references first, so *spec* need only
    carry the CRD fields; ``prefixes`` and ``ip_version`` are derived here.
    """
    resolved = nautobot_module.resolve_spec(spec, cache, namespace)
    name = resolved["name"]
    ip_version = validate_prefixes(resolved)
    address_scope = ensure_address_scope(conn, resolved, ip_version)
    address_scope_id = resource_id(address_scope) if address_scope else None
    desired = _desired_attrs(resolved, address_scope_id)

    notes: list[str] = []
    pool = find_subnet_pool(conn, resolved)
    _check_default_conflict(conn, resolved, ip_version, pool)
    if not pool:
        LOG.info(
            "Creating subnet pool %s address_scope_id=%s prefixes=%s",
            name,
            address_scope_id,
            resolved["prefixes"],
        )
        pool = conn.network.create_subnet_pool(**desired)
    else:
        LOG.info("Subnet pool %s already exists", name)
        _validate_existing(pool, resolved, ip_version)
        updates = _update_attrs(pool, desired)
        removed = _prefixes_removed(
            list(get_value(pool, "prefixes", default=[]) or []),
            resolved["prefixes"],
        )
        if removed:
            # Neutron rejects a shrinking prefix update (409); pushing it would
            # fail every cycle. Keep the existing prefixes, converge the rest,
            # and surface the drift for an operator to resolve.
            notes.append(
                f"Neutron subnet pool {name!r} still holds prefixes no longer "
                f"referenced in Nautobot ({', '.join(removed)}); Neutron does "
                "not allow removing prefixes from a pool, so drain and delete "
                "the pool to remove them"
            )
            updates.pop("prefixes", None)
        if updates:
            LOG.info("Reconciling subnet pool %s fields %s", name, sorted(updates))
            pool = conn.network.update_subnet_pool(pool, **updates)

    _ensure_tags(conn, pool, resolved)
    LOG.info(
        "Reconciled subnet pool: %s",
        json.dumps(render_subnet_pool(pool), sort_keys=True),
    )
    return notes
