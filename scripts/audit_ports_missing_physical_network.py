#!/usr/bin/env python3
"""Audit and repair Neutron ports missing binding_profile.physical_network.

Dry-run is the default. Pass --execute to write the baremetal port
physical_network back to the Neutron port binding_profile.

Output format:
    NODE_ID<TAB>PORT_ID<TAB>NAME<TAB>NETWORK_ID<TAB>
    BAREMETAL_PORT_PHYSICAL_NETWORK<TAB>REASON
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

LOG = logging.getLogger(__name__)

BINDING_PROFILE_FIELDS = ("binding_profile", "binding:profile")
BINDING_HOST_ID_FIELDS = ("binding_host_id", "binding:host_id")
BINDING_VNIC_TYPE_FIELDS = ("binding_vnic_type", "binding:vnic_type")
DEFAULT_NO_MATCH_REASON = (
    "no Ironic baremetal port matched any local_link_information entry"
)
ID_PORT_FIELDS = ["id"]
PORT_FIELDS = [
    "id",
    "name",
    "network_id",
    "binding:host_id",
    "binding:profile",
]
TERMINAL_LOOKUP_FAILURE_PREFIXES = (
    "baremetal lookup failed:",
    "OpenStack connection does not expose a baremetal service",
    "OpenStack baremetal service does not expose ports()",
)
OUTPUT_COLUMNS = (
    "NODE_ID",
    "PORT_ID",
    "NAME",
    "NETWORK_ID",
    "BAREMETAL_PORT_PHYSICAL_NETWORK",
    "REASON",
)
OUTPUT_HEADER = "\t".join(OUTPUT_COLUMNS)
_MISSING = object()


@dataclass(frozen=True)
class PortCandidate:
    """A port candidate yielded by one of the Neutron scan strategies."""

    port: Any | None
    has_binding_profile_field: bool = False


@dataclass(frozen=True)
class AuditResult:
    records: list[dict[str, Any]]
    scanned: int
    saw_binding_profile_field: bool = False


@dataclass(frozen=True)
class NeutronPortRecord:
    port_id: str | None
    port_name: str | None
    network_id: str | None
    mac_address: Any
    device_id: Any
    device_owner: Any
    status: Any
    binding_host_id: str | None
    binding_vnic_type: str | None
    binding_profile: dict[str, Any]
    physical_network: Any
    baremetal_port_physical_network: str | None = None
    reason: str | None = None

    @classmethod
    def from_port(
        cls,
        port: Any,
        binding_profile: dict[str, Any],
    ) -> NeutronPortRecord:
        return cls(
            port_id=port_id(port),
            port_name=port_name(port),
            network_id=port_network_id(port),
            mac_address=get_value(port, "mac_address"),
            device_id=get_value(port, "device_id"),
            device_owner=get_value(port, "device_owner"),
            status=get_value(port, "status"),
            binding_host_id=binding_host_id(port),
            binding_vnic_type=binding_vnic_type(port),
            binding_profile=binding_profile,
            physical_network=binding_profile.get("physical_network"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "port_id": self.port_id,
            "port_name": self.port_name,
            "network_id": self.network_id,
            "mac_address": self.mac_address,
            "device_id": self.device_id,
            "device_owner": self.device_owner,
            "status": self.status,
            "binding_host_id": self.binding_host_id,
            "binding_vnic_type": self.binding_vnic_type,
            "binding_profile": self.binding_profile,
            "physical_network": self.physical_network,
            "baremetal_port_physical_network": self.baremetal_port_physical_network,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BaremetalPhysicalNetworkLookup:
    physical_network: str | None
    reason: str | None

    @classmethod
    def from_tuple(
        cls,
        result: tuple[str | None, str | None],
    ) -> BaremetalPhysicalNetworkLookup:
        physical_network, reason = result
        return cls(physical_network=physical_network, reason=reason)

    def as_tuple(self) -> tuple[str | None, str | None]:
        return self.physical_network, self.reason

    def is_terminal_failure(self) -> bool:
        return bool(
            self.reason and self.reason.startswith(TERMINAL_LOOKUP_FAILURE_PREFIXES)
        )


@dataclass(frozen=True)
class BaremetalPortPhysicalNetwork:
    value: str | None
    reason: str | None

    def to_record_update(self) -> dict[str, Any]:
        return {
            "baremetal_port_physical_network": self.value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FixSummary:
    updated: int = 0
    failed: int = 0
    skipped: int = 0

    def as_tuple(self) -> tuple[int, int, int]:
        return self.updated, self.failed, self.skipped


def _resource_value(resource: Any, name: str) -> Any:
    if isinstance(resource, dict):
        return resource[name] if name in resource else _MISSING

    getter = getattr(resource, "get", None)
    if callable(getter):
        try:
            value = getter(name, _MISSING)
        except TypeError:
            try:
                value = getter(name)
            except Exception:
                value = _MISSING
        except Exception:
            value = _MISSING

        if value is not _MISSING:
            return value

    return getattr(resource, name, _MISSING)


def get_value(resource: Any, *names: str) -> Any:
    for name in names:
        value = _resource_value(resource, name)
        if value is not _MISSING and value is not None:
            return value
    return None


def has_field(resource: Any, *names: str) -> bool:
    return any(_resource_value(resource, name) is not _MISSING for name in names)


def has_value(value: Any) -> bool:
    return value not in (None, "")


def normalize_binding_profile(port: Any) -> dict[str, Any]:
    neutron_port_id = get_value(port, "id") or "<unknown>"
    raw_profile = get_value(port, *BINDING_PROFILE_FIELDS)

    if raw_profile in (None, ""):
        return {}
    if isinstance(raw_profile, dict):
        return raw_profile
    if isinstance(raw_profile, str):
        try:
            profile = json.loads(raw_profile)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"port {neutron_port_id} has invalid JSON binding_profile"
            ) from exc
        if isinstance(profile, dict):
            return profile
        raise ValueError(f"port {neutron_port_id} binding_profile is not a JSON object")

    raise ValueError(
        f"port {neutron_port_id} binding_profile has unsupported type "
        f"{type(raw_profile).__name__}"
    )


def local_link_information(binding_profile: dict[str, Any]) -> list[Any]:
    value = binding_profile.get("local_link_information")
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    return [value]


def local_link_connections(binding_profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in local_link_information(binding_profile)
        if isinstance(entry, dict)
    ]


def port_id(port: Any) -> str | None:
    return get_value(port, "id")


def port_name(port: Any) -> str | None:
    return get_value(port, "name")


def port_network_id(port: Any) -> str | None:
    return get_value(port, "network_id")


def binding_host_id(port: Any) -> str | None:
    return get_value(port, *BINDING_HOST_ID_FIELDS)


def binding_vnic_type(port: Any) -> str | None:
    return get_value(port, *BINDING_VNIC_TYPE_FIELDS)


def port_record(
    port: Any,
    binding_profile: dict[str, Any],
) -> dict[str, Any]:
    return NeutronPortRecord.from_port(port, binding_profile).to_dict()


def is_missing_physical_network_record(record: dict[str, Any]) -> bool:
    return bool(local_link_information(record["binding_profile"])) and not has_value(
        record["physical_network"]
    )


def get_baremetal_service(conn: Any) -> Any:
    service = getattr(conn, "baremetal", None)
    if service is None:
        raise RuntimeError("OpenStack connection does not expose a baremetal service")

    ports = getattr(service, "ports", None)
    if not callable(ports):
        raise RuntimeError("OpenStack baremetal service does not expose ports()")

    return ports


def _lookup_baremetal_port_physical_network(
    conn: Any,
    local_link_connection: dict[str, Any],
) -> BaremetalPhysicalNetworkLookup:
    try:
        ports = get_baremetal_service(conn)
    except RuntimeError as exc:
        return BaremetalPhysicalNetworkLookup(None, str(exc))

    try:
        port = next(ports(details=True, local_link_connection=local_link_connection))
    except StopIteration:
        return BaremetalPhysicalNetworkLookup(None, DEFAULT_NO_MATCH_REASON)
    except Exception as exc:
        return BaremetalPhysicalNetworkLookup(
            None,
            f"baremetal lookup failed: {exc}",
        )

    physical_network = get_value(port, "physical_network")
    if has_value(physical_network):
        return BaremetalPhysicalNetworkLookup(physical_network, None)

    return BaremetalPhysicalNetworkLookup(
        None,
        "matching Ironic baremetal port has no physical_network",
    )


def lookup_baremetal_port_physical_network(
    conn: Any,
    local_link_connection: dict[str, Any],
) -> tuple[str | None, str | None]:
    return _lookup_baremetal_port_physical_network(
        conn,
        local_link_connection,
    ).as_tuple()


def derive_baremetal_port_physical_network(
    conn: Any,
    binding_profile: dict[str, Any],
) -> dict[str, Any]:
    candidates = local_link_connections(binding_profile)
    if not candidates:
        return BaremetalPortPhysicalNetwork(
            None,
            "binding_profile has no usable local_link_information",
        ).to_record_update()

    last_reason = DEFAULT_NO_MATCH_REASON
    for local_link_connection in candidates:
        lookup = BaremetalPhysicalNetworkLookup.from_tuple(
            lookup_baremetal_port_physical_network(conn, local_link_connection)
        )
        if has_value(lookup.physical_network):
            return BaremetalPortPhysicalNetwork(
                lookup.physical_network,
                None,
            ).to_record_update()

        if lookup.is_terminal_failure():
            return BaremetalPortPhysicalNetwork(
                None,
                lookup.reason,
            ).to_record_update()

        if lookup.reason:
            last_reason = lookup.reason

    return BaremetalPortPhysicalNetwork(None, last_reason).to_record_update()


def derive_physical_network(
    conn: Any,
    binding_profile: dict[str, Any],
) -> dict[str, Any]:
    return derive_baremetal_port_physical_network(conn, binding_profile)


def build_port_record(
    conn: Any,
    port: Any,
    derive_baremetal: bool = False,
) -> dict[str, Any] | None:
    neutron_port_id = port_id(port) or "<unknown>"

    try:
        profile = normalize_binding_profile(port)
    except ValueError as exc:
        LOG.debug("skipping port %s: %s", neutron_port_id, exc)
        return None

    record = port_record(port, profile)
    if not is_missing_physical_network_record(record):
        return None

    if derive_baremetal:
        record.update(derive_baremetal_port_physical_network(conn, profile))

    return record


def detailed_neutron_port(conn: Any, port: Any) -> Any | None:
    neutron_port_id = port_id(port)
    if not neutron_port_id:
        LOG.debug("skipping port without id: %r", port)
        return None

    try:
        return conn.network.get_port(neutron_port_id)
    except Exception as exc:
        LOG.debug(
            "skipping port %s: unable to fetch port details: %s",
            neutron_port_id,
            exc,
        )
        return None


def build_missing_physical_network_record(
    conn: Any,
    port: Any,
    derive_baremetal: bool = True,
) -> dict[str, Any] | None:
    detailed_port = detailed_neutron_port(conn, port)
    if detailed_port is None:
        return None

    return build_port_record(conn, detailed_port, derive_baremetal)


def fast_port_candidates(conn: Any) -> Iterable[PortCandidate]:
    for port in conn.network.ports(fields=PORT_FIELDS):
        yield PortCandidate(
            port=port,
            has_binding_profile_field=has_field(port, *BINDING_PROFILE_FIELDS),
        )


def detailed_port_candidates(conn: Any) -> Iterable[PortCandidate]:
    for port in conn.network.ports(fields=ID_PORT_FIELDS):
        detailed_port = detailed_neutron_port(conn, port)
        if detailed_port is not None:
            yield PortCandidate(port=detailed_port)


def scan_candidates(
    conn: Any,
    candidates: Iterable[PortCandidate],
    derive_baremetal: bool = False,
) -> AuditResult:
    records: list[dict[str, Any]] = []
    scanned = 0
    saw_binding_profile_field = False

    for candidate in candidates:
        scanned += 1
        saw_binding_profile_field = (
            saw_binding_profile_field or candidate.has_binding_profile_field
        )

        if candidate.port is None:
            continue

        record = build_port_record(conn, candidate.port, derive_baremetal)
        if record is not None:
            records.append(record)

    return AuditResult(
        records=records,
        scanned=scanned,
        saw_binding_profile_field=saw_binding_profile_field,
    )


def scan_fast(conn: Any, derive_baremetal: bool = False) -> AuditResult:
    return scan_candidates(conn, fast_port_candidates(conn), derive_baremetal)


def scan_slow(conn: Any, derive_baremetal: bool = False) -> AuditResult:
    return scan_candidates(conn, detailed_port_candidates(conn), derive_baremetal)


def build_missing_physical_network_report(
    conn: Any,
    derive_baremetal: bool = False,
) -> list[dict[str, Any]]:
    result = scan_fast(conn, derive_baremetal)
    if result.saw_binding_profile_field:
        return result.records

    return scan_slow(conn, derive_baremetal).records


def apply_fix(conn: Any, record: dict[str, Any]) -> bool:
    profile = dict(record["binding_profile"])
    profile["physical_network"] = record["baremetal_port_physical_network"]

    try:
        conn.network.update_port(record["port_id"], binding_profile=profile)
    except Exception as exc:
        LOG.error("failed to update port %s: %s", record["port_id"], exc)
        return False

    return True


def apply_fix_summary(conn: Any, records: list[dict[str, Any]]) -> FixSummary:
    updated = 0
    failed = 0
    skipped = 0

    for record in records:
        if not record.get("baremetal_port_physical_network"):
            skipped += 1
            continue

        if apply_fix(conn, record):
            updated += 1
        else:
            failed += 1

    return FixSummary(updated=updated, failed=failed, skipped=skipped)


def apply_fixes(
    conn: Any,
    records: list[dict[str, Any]],
) -> tuple[int, int, int]:
    return apply_fix_summary(conn, records).as_tuple()


def record_to_tsv(record: dict[str, Any]) -> str:
    values = (
        record.get("binding_host_id"),
        record.get("port_id"),
        record.get("port_name"),
        record.get("network_id"),
        record.get("baremetal_port_physical_network"),
        record.get("reason"),
    )
    return "\t".join("" if value is None else str(value) for value in values)


def print_tsv_report(records: list[dict[str, Any]]) -> None:
    print(OUTPUT_HEADER, flush=True)
    for record in records:
        print(record_to_tsv(record), flush=True)


def connect_openstack(os_cloud: str | None) -> Any:
    try:
        import openstack
    except ImportError as exc:
        raise RuntimeError("openstacksdk is required to run this script") from exc

    return openstack.connect(cloud=os_cloud)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit Neutron ports whose binding_profile has local_link_information "
            "but is missing physical_network."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  audit_ports_missing_physical_network.py --os-cloud uc-iad3-dev\n"
            "  audit_ports_missing_physical_network.py --os-cloud uc-iad3-dev "
            "--derive-baremetal-port-physical-network\n"
            "  audit_ports_missing_physical_network.py --os-cloud uc-iad3-dev --execute"
        ),
    )
    parser.add_argument(
        "--os-cloud",
        metavar="CLOUD",
        default=None,
        help="OpenStack cloud name from clouds.yaml. Defaults to OS_CLOUD.",
    )
    parser.add_argument(
        "--derive-baremetal-port-physical-network",
        action="store_true",
        help=(
            "Look up matching Ironic baremetal ports to populate "
            "BAREMETAL_PORT_PHYSICAL_NETWORK. This is slower."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Update affected ports. Implies "
            "--derive-baremetal-port-physical-network."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    try:
        conn = connect_openstack(args.os_cloud)
    except Exception as exc:
        print(f"ERROR: failed to connect to OpenStack: {exc}", file=sys.stderr)
        return 1

    derive_baremetal = args.derive_baremetal_port_physical_network or args.execute

    try:
        result = scan_fast(conn, derive_baremetal)
    except Exception as exc:
        print(f"error: fast scan failed: {exc}", file=sys.stderr)
        return 1

    if not result.saw_binding_profile_field:
        print(
            "binding_profile was not present in the list response; falling back "
            "to per-port fetches",
            file=sys.stderr,
        )
        try:
            result = scan_slow(conn, derive_baremetal)
        except Exception as exc:
            print(f"error: fallback scan failed: {exc}", file=sys.stderr)
            return 1

    fix_summary = (
        apply_fix_summary(conn, result.records) if args.execute else FixSummary()
    )
    print_tsv_report(result.records)

    print(
        f"done: scanned {result.scanned} ports, matched {len(result.records)}",
        file=sys.stderr,
    )
    if fix_summary.skipped:
        LOG.warning(
            "skipped %d port(s) without a baremetal port physical_network",
            fix_summary.skipped,
        )
    if fix_summary.failed:
        LOG.error("failed to update %d port(s)", fix_summary.failed)

    return 1 if fix_summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
