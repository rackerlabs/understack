"""Resolve a NeutronSubnetPool CR's Nautobot prefix references into CIDRs.

The CRD's top level is the OpenStack subnet-pool contract (name, address scope,
prefix lengths, ...) and is the single source of truth for the pool's policy.
``spec.nautobot`` is the reference contract: where Nautobot is, which prefixes
supply this pool's CIDRs, and optional guardrails each prefix must satisfy.

Nautobot owns only the CIDRs -- IP allocation is its job -- so this module
loads each referenced prefix, checks the ``require`` guardrails, and hands the
reconcile step the resolved ``prefixes`` and ``ip_version``. It reads nothing
policy-shaped from Nautobot: the pool name, address scope, and prefix lengths
come from the CR spec, not from prefix ``custom_fields``.

The reconcile step consumes the normalized spec this module returns, so it never
reads Nautobot itself.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from ipaddress import ip_network
from typing import Any

import pynautobot

from openstack_sync.plugins.common import ConfigError
from openstack_sync.utils import read_secret_key

LOG = logging.getLogger(__name__)

#: Cluster site (Nautobot leaf Site name) injected by the deployment. Used as
#: the default require.location when a CR does not set one.
SITE_ENV = "UNDERSTACK_SITE"

#: Condition reason reported when a referenced Nautobot prefix no longer exists.
PREFIX_NOT_FOUND_REASON = "NautobotPrefixMissing"


@dataclass(frozen=True)
class NautobotPrefix:
    """Subset of Nautobot Prefix fields needed for subnet-pool planning."""

    id: str | None
    prefix: str
    status: str | None
    prefix_type: str | None
    namespace: str | None
    tags: tuple[str, ...]


def resolve_spec(
    spec: dict[str, Any], cache: dict[str, Any], namespace: str
) -> dict[str, Any]:
    """Return *spec* enriched with the CIDRs Nautobot is authoritative for.

    Loads every referenced prefix, checks the optional ``require`` guardrails,
    then attaches the resolved ``prefixes`` and ``ip_version``. The pool's
    policy (name, address scope, prefix lengths) is already on *spec* and is
    left untouched. The returned dict is a shallow copy carrying Neutron-shaped
    fields only, so the reconcile step never touches Nautobot. Raises
    :exc:`ConfigError` when a referenced prefix is missing, fails the
    guardrails, or the group mixes IP versions.
    """
    nautobot_spec = _required_mapping(spec, "nautobot", "spec")
    name = _required_string(spec, "name")
    nautobot_url = _required_string(nautobot_spec, "url")
    client = _nautobot_client(spec, cache, namespace)
    prefix_refs = _nautobot_prefix_refs(spec)
    requirements = _nautobot_requirements(spec)
    prefixes = load_nautobot_prefixes(
        client,
        prefix_refs,
        nautobot_url=nautobot_url,
        require_location=_require_location(requirements),
    )
    _validate_prefixes(prefixes, requirements)

    resolved = dict(spec)
    resolved["prefixes"] = [prefix.prefix for prefix in prefixes]
    resolved["ip_version"] = _subnet_pool_ip_version(name, prefixes)
    # Kept alongside the flat CIDR list above (which reconcile.py validates and
    # sends to Neutron) so the plugin can report each prefix's Nautobot id and
    # UI link on the CR status without reconcile.py needing to know about
    # Nautobot at all.
    resolved["nautobot_prefix_links"] = [
        {
            "id": prefix.id,
            "cidr": prefix.prefix,
            "url": prefix_url(nautobot_url, prefix.id),
        }
        for prefix in prefixes
        if prefix.id
    ]

    LOG.info(
        "Resolved subnet pool %s from %s Nautobot prefix(es): %s",
        name,
        len(prefixes),
        ", ".join(prefix.prefix for prefix in prefixes),
    )
    return resolved


def prefix_url(nautobot_url: str, prefix_id: str) -> str:
    """Return the Nautobot UI URL for one prefix record.

    Mirrors the URL shape used by the ``link.argocd.argoproj.io/external-link``
    annotation hand-authored on today's CRs: ``<nautobot_url>/ipam/prefixes/
    <id>/``. Centralised here so every consumer (CR status, future tooling)
    builds the same link the same way.
    """
    return f"{nautobot_url.rstrip('/')}/ipam/prefixes/{prefix_id}/"


# ---------------------------------------------------------------------------
# Nautobot client and prefix loading
# ---------------------------------------------------------------------------


def _nautobot_client(
    spec: dict[str, Any], cache: dict[str, Any], namespace: str
) -> Any:
    nautobot_spec = _required_mapping(spec, "nautobot", "spec")
    token_ref = _required_mapping(nautobot_spec, "tokenSecretRef", "spec.nautobot")
    url = _required_string(nautobot_spec, "url")
    api_version = str(nautobot_spec.get("api_version") or "2.0")
    secret_name = _required_string(token_ref, "secretName")
    secret_key = _required_string(token_ref, "key")

    cache_key = (
        "nautobot_client",
        url,
        api_version,
        secret_name,
        secret_key,
        namespace,
    )
    if cache_key not in cache:
        token = read_secret_key(secret_name, secret_key, namespace).strip()
        cache[cache_key] = pynautobot.api(
            url,
            token=token,
            api_version=api_version,
            retries=3,
        )
    return cache[cache_key]


def load_nautobot_prefixes(
    client: Any,
    prefix_refs: list[dict[str, str]],
    *,
    nautobot_url: str,
    require_location: str | None = None,
) -> list[NautobotPrefix]:
    """Load prefixes from Nautobot by id, filtered by *require_location*."""
    prefixes: list[NautobotPrefix] = []
    for ref in prefix_refs:
        prefix_id = ref["id"]
        link = prefix_url(nautobot_url, prefix_id)
        query: dict[str, str] = {"id": prefix_id}
        if require_location:
            query["location"] = require_location
        try:
            record = client.ipam.prefixes.get(**query)
        except pynautobot.RequestError as exc:
            if require_location and _is_invalid_location_error(exc, require_location):
                raise ConfigError(
                    f"spec.nautobot.require.location {require_location!r} is not a "
                    "valid Nautobot location; use the exact leaf Site name "
                    "(for example 'iad3-dev')"
                ) from exc
            raise ConfigError(
                f"Nautobot prefix lookup failed for id {prefix_id} ({link}): {exc}"
            ) from exc

        if record is None:
            if require_location:
                raise ConfigError(
                    f"Nautobot prefix {prefix_id} ({link}) was not found under "
                    f"location {require_location!r}: it does not exist or is not "
                    "associated with that location (spec.nautobot.require.location)",
                    reason=PREFIX_NOT_FOUND_REASON,
                )
            raise ConfigError(
                f"Nautobot prefix {prefix_id} ({link}) was not found",
                reason=PREFIX_NOT_FOUND_REASON,
            )
        prefixes.append(_prefix_from_record(record))
    return prefixes


def _is_invalid_location_error(
    exc: pynautobot.RequestError, require_location: str
) -> bool:
    """Return True when Nautobot rejected an unknown ``location`` (HTTP 400)."""
    response = getattr(exc, "req", None)
    if getattr(response, "status_code", None) != 400:
        return False
    error_text = str(getattr(exc, "error", "") or "")
    return "location" in error_text or require_location in error_text


def _nautobot_prefix_refs(spec: dict[str, Any]) -> list[dict[str, str]]:
    nautobot_spec = _required_mapping(spec, "nautobot", "spec")
    raw_refs = nautobot_spec.get("prefix_refs")
    if not isinstance(raw_refs, list) or not raw_refs:
        raise ConfigError("spec.nautobot.prefix_refs must be a non-empty list")

    refs: list[dict[str, str]] = []
    for index, raw_ref in enumerate(raw_refs):
        if not isinstance(raw_ref, dict):
            raise ConfigError(f"spec.nautobot.prefix_refs[{index}] must be a mapping")
        prefix_id = _field_text(raw_ref.get("id"))
        if not prefix_id:
            raise ConfigError(f"spec.nautobot.prefix_refs[{index}].id must be set")
        refs.append({"id": prefix_id})
    return refs


def _nautobot_requirements(spec: dict[str, Any]) -> dict[str, Any]:
    nautobot_spec = _required_mapping(spec, "nautobot", "spec")
    requirements = nautobot_spec.get("require") or {}
    if not isinstance(requirements, dict):
        raise ConfigError("spec.nautobot.require must be a mapping")
    return requirements


def _require_location(requirements: dict[str, Any]) -> str | None:
    """Return require.location, defaulting to the operator's UNDERSTACK_SITE."""
    return _field_text(requirements.get("location")) or os.environ.get(SITE_ENV) or None


# ---------------------------------------------------------------------------
# Guardrail validation
# ---------------------------------------------------------------------------


def _validate_prefixes(
    prefixes: list[NautobotPrefix], requirements: dict[str, Any]
) -> None:
    for prefix in prefixes:
        errors = _prefix_requirement_errors(prefix, requirements)
        if errors:
            prefix_id = prefix.id or prefix.prefix
            raise ConfigError(
                f"Nautobot prefix {prefix_id} does not satisfy "
                f"spec.nautobot.require: {'; '.join(errors)}"
            )


def _prefix_requirement_errors(
    prefix: NautobotPrefix, requirements: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    expected_status = _field_text(requirements.get("status"))
    if expected_status and prefix.status != expected_status:
        errors.append(f"status is {prefix.status!r}, expected {expected_status!r}")

    expected_type = _field_text(requirements.get("type"))
    if expected_type and prefix.prefix_type != expected_type:
        errors.append(f"type is {prefix.prefix_type!r}, expected {expected_type!r}")

    expected_namespace = _field_text(requirements.get("namespace"))
    if expected_namespace and prefix.namespace != expected_namespace:
        errors.append(
            f"namespace is {prefix.namespace!r}, expected {expected_namespace!r}"
        )

    # require.location is enforced via the ?location= query in
    # load_nautobot_prefixes, not checked here.

    expected_tags = _requirement_tags(requirements)
    missing_tags = [tag for tag in expected_tags if tag not in prefix.tags]
    if missing_tags:
        errors.append(f"missing tags {missing_tags!r}")
    return errors


def _requirement_tags(requirements: dict[str, Any]) -> tuple[str, ...]:
    raw_tags = requirements.get("tags")
    if raw_tags is None:
        return ()
    if not isinstance(raw_tags, list):
        raise ConfigError("spec.nautobot.require.tags must be a list")
    return tuple(tag for tag in (_field_text(tag) for tag in raw_tags) if tag)


# ---------------------------------------------------------------------------
# Record extraction
# ---------------------------------------------------------------------------


def _prefix_from_record(record: Any) -> NautobotPrefix:
    prefix = _field_text(record.prefix)
    if not prefix:
        raise ConfigError(f"Nautobot prefix record has no prefix value: {record!r}")

    return NautobotPrefix(
        id=_field_text(record.id) or None,
        prefix=prefix,
        status=_field_text(record.status) or None,
        prefix_type=_field_text(record.type) or None,
        namespace=_field_text(record.namespace) or None,
        tags=_field_texts(record.tags),
    )


def _prefix_ip_version(prefix: NautobotPrefix) -> int:
    try:
        return ip_network(prefix.prefix, strict=False).version
    except ValueError as exc:
        raise ConfigError(
            f"Nautobot prefix {prefix.prefix!r} is not valid CIDR notation"
        ) from exc


def _subnet_pool_ip_version(name: str, prefixes: list[NautobotPrefix]) -> int:
    if not prefixes:
        raise ConfigError("spec.nautobot.prefix_refs must resolve at least one prefix")
    versions = {_prefix_ip_version(prefix) for prefix in prefixes}
    if len(versions) != 1:
        prefix_values = ", ".join(prefix.prefix for prefix in prefixes)
        raise ConfigError(
            f"Nautobot subnet pool {name!r} contains mixed IP versions: {prefix_values}"
        )
    return versions.pop()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _required_mapping(
    source: dict[str, Any], key: str, parent_path: str
) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"{parent_path}.{key} must be set")
    return value


def _required_string(source: dict[str, Any], key: str) -> str:
    value = _field_text(source.get(key))
    if not value:
        raise ConfigError(f"{key} must be set")
    return value


def _field_texts(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list | tuple):
        return tuple(_field_text(item) for item in value if _field_text(item))
    return (_field_text(value),) if _field_text(value) else ()


def _field_text(value: Any) -> str:
    """Extract a comparable string from a Nautobot field.

    Nautobot related fields come back in several shapes and pynautobot wraps
    them as ``Record`` objects, so a single accessor is not enough:

    - ``status``/``namespace``: carry a ``name`` ("Active", "Rackspace").
    - ``type``: a choice field with ``value``/``label`` ({"value": "pool",
      "label": "Pool"}); we compare against the machine value ("pool").
    - ``tags``: Records whose value is only reachable via ``str()`` (``display``).

    Order matters: ``name`` first, then the choice ``value``, then ``str()``
    (which pynautobot defines as display/name/label). ``type`` is handled before
    the ``str()`` fallback because ``str()`` would yield the human label "Pool"
    rather than the value "pool" the guardrail expects.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        text = value.get("name") or value.get("value") or value.get("display") or ""
        return str(text).strip()
    # pynautobot Record (or similar): prefer name, then choice value, then str().
    name = getattr(value, "name", None)
    if name:
        return str(name).strip()
    choice_value = getattr(value, "value", None)
    if choice_value:
        return str(choice_value).strip()
    return str(value).strip()
