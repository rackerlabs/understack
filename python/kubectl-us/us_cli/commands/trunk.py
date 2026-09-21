"""Audit the trunk state on baremetal trunks.

ml2/ovn used to manage any trunk whose parent port had a Logical_Switch_Port.
A baremetal parent has one -- type=external, purely so OVN can schedule an HA
chassis group -- while the VLANs are programmed on the leaf switch by undersync.
LP #2167105 stops it managing these trunks, but the subport state it already
wrote stays: a stale ovs vif_type binding and a binding profile that may not
match the trunk.

neutron-understack now owns the subport's binding profile: parent_name and tag
are what Nova reads to put the VLAN link in network_data.json, so they must
match the trunk. ml2/ovn copies the same keys onto the subport's LSP
(ovn_client._get_port_options). That is expected and left alone.

binding:profile and vif_type are the driver's to write, not ours, so the audit
changes nothing. Rebinding the parent port makes neutron-understack rewrite
every subport's binding, and Ironic's reattach_networking service step does
exactly that, so a trunk whose subport bindings have drifted is reported with
the command to run for its node.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any

import typer

from us_cli import osclient
from us_cli.connection import ConnectionContext
from us_cli.connection import print_connection_banner

BAREMETAL_VNIC_TYPE = "baremetal"
BAREMETAL_VIF_TYPE = "other"
SUBPORT_DEVICE_OWNER = "trunk:subport"
UNBOUND_VIF_TYPE = "unbound"
# Port ids per ports() request, each about 37 characters of URL.
PORT_QUERY_CHUNK = 100


app = typer.Typer(
    no_args_is_help=True,
    help="Audit baremetal trunk subport state.",
)


@dataclass(frozen=True)
class Finding:
    """One audit assertion."""

    status: str
    check: str
    detail: str


@dataclass
class TrunkState:
    """A baremetal trunk with the Neutron ports the audit compares."""

    trunk: Any
    parent: Any
    subports: list[Any]
    # Subports the trunk names that Neutron has no port for.
    missing: list[str] = field(default_factory=list)


def _value(resource: Any, key: str, default=None) -> Any:
    """Read an SDK resource or dict without depending on its concrete type."""
    value = getattr(resource, key, None)
    if value is not None:
        return value
    getter = getattr(resource, "get", None)
    return getter(key, default) if getter else default


def _check(
    findings: list[Finding], condition: bool, name: str, good: str, bad: str
) -> None:
    findings.append(
        Finding("PASS" if condition else "FAIL", name, good if condition else bad)
    )


def _label(trunk) -> str:
    return f"{_value(trunk, 'name') or '(unnamed)'} ({_value(trunk, 'id')})"


def _parent_is_bound(parent) -> bool:
    """The same predicate neutron-understack's trunk driver binds on."""
    profile = _value(parent, "binding_profile") or {}
    return _value(parent, "binding_vif_type") == BAREMETAL_VIF_TYPE and bool(
        profile.get("physical_network")
    )


def _expected_status(state: TrunkState) -> str:
    return "ACTIVE" if _parent_is_bound(state.parent) else "DOWN"


def _expected_vif_type(state: TrunkState) -> str:
    """A subport is bound to the switchport, via its parent, while that is."""
    return BAREMETAL_VIF_TYPE if _parent_is_bound(state.parent) else UNBOUND_VIF_TYPE


def _is_trunk_subport(port) -> bool:
    """Only ordinary trunk subports are safe for this migration to alter."""
    return _value(port, "device_owner") == SUBPORT_DEVICE_OWNER


def _status_findings(state: TrunkState) -> list[Finding]:
    expected = _expected_status(state)
    parent_state = "bound" if _parent_is_bound(state.parent) else "unbound"
    findings: list[Finding] = []
    status = _value(state.trunk, "status")
    _check(
        findings,
        status == expected,
        "trunk status",
        expected,
        f"expected {expected} for a {parent_state} parent, found {status}; "
        "a successful Undersync reconciliation corrects the status",
    )
    for port in state.subports:
        if not _is_trunk_subport(port):
            continue
        status = _value(port, "status")
        _check(
            findings,
            status == expected,
            f"subport {_value(port, 'id')}: status",
            expected,
            f"expected {expected} for a {parent_state} parent, found {status}",
        )
    return findings


def _expected_profile(state: TrunkState, port) -> dict[str, Any]:
    """The parent_name/tag Nova needs for this subport, from the trunk itself."""
    port_id = _value(port, "id")
    for subport in _value(state.trunk, "sub_ports") or []:
        if subport["port_id"] == port_id:
            return {
                "parent_name": _value(state.trunk, "port_id"),
                "tag": subport["segmentation_id"],
            }
    return {}


def _profile_drift(state: TrunkState, port) -> dict[str, Any]:
    """The expected profile keys the port does not carry, or carries wrongly."""
    profile = _value(port, "binding_profile") or {}
    return {
        key: value
        for key, value in _expected_profile(state, port).items()
        if profile.get(key) != value
    }


def _resolve_trunks(conn, name_or_id: str | None) -> list[Any]:
    if not name_or_id:
        return list(conn.network.trunks())
    trunk = conn.network.find_trunk(name_or_id)
    if trunk is None:
        raise LookupError(f"trunk {name_or_id!r} not found")
    return [trunk]


def _fetch_ports(conn, port_ids: set[str]) -> dict[str, Any]:
    """Fetch ports by id, PORT_QUERY_CHUNK ids per ports() request.

    Ports that do not exist are absent from the result.
    """
    wanted = sorted(port_ids)
    return {
        _value(port, "id"): port
        for start in range(0, len(wanted), PORT_QUERY_CHUNK)
        for port in conn.network.ports(id=wanted[start : start + PORT_QUERY_CHUNK])
    }


def _load_states(
    conn, trunks: list[Any]
) -> tuple[list[TrunkState], list[str], list[str]]:
    """Load each baremetal trunk's parent and subports.

    Returns the states, the trunks skipped as ovn-owned, and the trunks that
    could not be loaded. The parents are fetched first so that only baremetal
    trunks have their subports fetched.
    """
    parents = _fetch_ports(conn, {_value(trunk, "port_id") for trunk in trunks})
    skipped: list[str] = []
    errors: list[str] = []
    baremetal: list[tuple[Any, Any]] = []
    for trunk in trunks:
        parent = parents.get(_value(trunk, "port_id"))
        if parent is None:
            errors.append(
                f"trunk {_label(trunk)}: parent port {_value(trunk, 'port_id')} "
                "not found"
            )
        elif _value(parent, "binding_vnic_type") != BAREMETAL_VNIC_TYPE:
            skipped.append(
                f"trunk {_label(trunk)}: parent port is not baremetal, "
                "so ml2/ovn still owns this trunk"
            )
        else:
            baremetal.append((trunk, parent))

    subports = _fetch_ports(
        conn,
        {
            subport["port_id"]
            for trunk, _ in baremetal
            for subport in _value(trunk, "sub_ports") or []
        },
    )
    states: list[TrunkState] = []
    for trunk, parent in baremetal:
        ids = [subport["port_id"] for subport in _value(trunk, "sub_ports") or []]
        missing = [port_id for port_id in ids if port_id not in subports]
        states.append(
            TrunkState(
                trunk,
                parent,
                [subports[port_id] for port_id in ids if port_id in subports],
                missing,
            )
        )
    return states, skipped, errors


def _audit_trunk(state: TrunkState) -> list[Finding]:
    findings = _status_findings(state)
    findings.extend(
        Finding("FAIL", f"subport {port_id}", "port not found")
        for port_id in state.missing
    )
    for port in state.subports:
        port_id = _value(port, "id")
        label = f"subport {port_id}"
        if not _is_trunk_subport(port):
            owner = _value(port, "device_owner") or "(empty)"
            findings.append(
                Finding(
                    "SKIP",
                    label,
                    f"device_owner={owner}; only {SUBPORT_DEVICE_OWNER} ports "
                    "are in scope",
                )
            )
            continue

        vif_type = _value(port, "binding_vif_type")
        _check(
            findings,
            vif_type == _expected_vif_type(state),
            f"{label}: binding vif_type",
            _expected_vif_type(state),
            f"expected {_expected_vif_type(state)}, found {vif_type or '(empty)'}",
        )
        drift = _profile_drift(state, port)
        expected = _expected_profile(state, port)
        profile = _value(port, "binding_profile") or {}
        _check(
            findings,
            not drift,
            f"{label}: binding profile",
            f"parent_name={expected.get('parent_name')}, tag={expected.get('tag')}",
            "expected "
            + ", ".join(f"{key}={value}" for key, value in drift.items())
            + "; found "
            + ", ".join(f"{key}={profile.get(key)}" for key in drift),
        )
    return findings


def _binding_drifted(state: TrunkState) -> bool:
    """Whether any in-scope subport's profile or vif_type is not what it should be."""
    return any(
        _profile_drift(state, port)
        or _value(port, "binding_vif_type") != _expected_vif_type(state)
        for port in state.subports
        if _is_trunk_subport(port)
    )


def _reattach_command(node: str) -> str:
    steps = '[{"interface": "network", "step": "reattach_networking"}]'
    return f"openstack baremetal node service {node} --service-steps '{steps}'"


def _print_fix(state: TrunkState) -> None:
    """Say how to have neutron-understack correct drifted subport bindings."""
    # Ironic binds the parent port with binding:host_id set to the node.
    node = _value(state.parent, "binding_host_id")
    if not node:
        print(
            "  The parent is unbound, so there is no node to reattach; "
            "neutron-understack corrects the subports when it is bound"
        )
        return
    print(
        "  To have neutron-understack correct the subports, rebind the parent "
        "without a reboot (the node must be active; its network is down while "
        "it rebinds):"
    )
    print(f"    {_reattach_command(node)}")


@app.command("audit")
def audit(
    ctx: typer.Context,
    name_or_id: str = typer.Argument(
        None, help="Neutron trunk name or ID (default: every baremetal trunk)"
    ),
) -> None:
    """Check baremetal trunk subports carry the binding profile Nova needs."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx, include_openstack=True)
    try:
        conn = osclient.get_connection(conn_ctx.os_cloud)
        states, skipped, errors = _load_states(conn, _resolve_trunks(conn, name_or_id))
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    print()
    for reason in skipped:
        print(f"SKIP  {reason}")
    for reason in errors:
        print(f"FAIL  {reason}")
    if not states and not errors:
        print("(no baremetal trunks found)")
        return

    failed = bool(errors)
    for state in states:
        print(f"\nTrunk {_label(state.trunk)}")
        parent_state = "bound" if _parent_is_bound(state.parent) else "unbound"
        print(f"Parent port: {_value(state.parent, 'id')} (baremetal, {parent_state})")
        findings = _audit_trunk(state)
        for finding in findings:
            print(f"  {finding.status:<4}  {finding.check}: {finding.detail}")
        failed = failed or any(finding.status == "FAIL" for finding in findings)
        if _binding_drifted(state):
            _print_fix(state)

    if failed:
        raise typer.Exit(1)
