"""Audit and clean up the trunk state ml2/ovn left behind on baremetal trunks.

ml2/ovn used to manage any trunk whose parent port had a Logical_Switch_Port.
A baremetal parent has one -- type=external, purely so OVN can schedule an HA
chassis group -- while the VLANs are programmed on the leaf switch by undersync.
So it wrote parent_name/tag into every subport's binding profile and LSP, which
mean nothing outside OVN, and pointed parent_name at an LSP on a different
logical switch. LP #2167105 stops it managing these trunks, but the rows it
already wrote stay: the code that used to remove them on subport delete now
returns early.

The subport's binding profile is the source of truth here, because ml2/ovn
derives the LSP's parent_name/tag from it (ovn_client._get_port_options). So
dropping those keys via Neutron makes ml2/ovn rewrite the LSP itself; the direct
NB clear is only for rows it did not catch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import typer

from us_cli import osclient
from us_cli import ovn
from us_cli.connection import ConnectionContext
from us_cli.connection import print_connection_banner

BAREMETAL_VNIC_TYPE = "baremetal"
BAREMETAL_VIF_TYPE = "other"
SUBPORT_DEVICE_OWNER = "trunk:subport"

#: binding:profile keys ml2/ovn's trunk driver wrote on subports.
STALE_PROFILE_KEYS = ("parent_name", "tag")
#: The LSP columns those keys end up in. Neutron converts a `tag` write into
#: `tag_request` (commands._tag_column_to_tag_request); northd then derives the
#: read-only `tag` column, and drops it once parent_name/tag_request are gone.
STALE_LSP_COLUMNS = ("parent_name", "tag_request")

app = typer.Typer(
    no_args_is_help=True,
    help="Audit and clean up baremetal trunk state left behind by ml2/ovn.",
)


@dataclass(frozen=True)
class Finding:
    """One audit assertion."""

    status: str
    check: str
    detail: str


@dataclass(frozen=True)
class SubportRepair:
    """The cleanup for one subport: a Neutron port update, then an NB clear."""

    port_id: str
    port_updates: dict[str, Any]
    clear_columns: tuple[str, ...]
    changes: tuple[str, ...]


@dataclass
class TrunkState:
    """A baremetal trunk with the Neutron and NB rows the audit compares."""

    trunk: Any
    parent: Any
    subports: list[Any]
    lsps: dict[str, dict]


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


def _lsp_rows(conn_ctx: ConnectionContext, port_ids: list[str]) -> dict[str, dict]:
    rows = ovn.nbctl_list_records(conn_ctx, "Logical_Switch_Port", port_ids)
    return {row["name"]: row for row in rows if row.get("name")}


def _stale_profile_keys(port) -> list[str]:
    profile = _value(port, "binding_profile") or {}
    return [key for key in STALE_PROFILE_KEYS if key in profile]


def _stale_lsp_columns(lsp: dict | None) -> tuple[str, ...]:
    if lsp is None:
        return ()
    return tuple(column for column in STALE_LSP_COLUMNS if ovn.as_list(lsp.get(column)))


def _resolve_trunks(conn, name_or_id: str | None) -> list[Any]:
    if not name_or_id:
        return list(conn.network.trunks())
    trunk = conn.network.find_trunk(name_or_id)
    if trunk is None:
        raise LookupError(f"trunk {name_or_id!r} not found")
    return [trunk]


def _load_states(
    conn, conn_ctx: ConnectionContext, trunks: list[Any]
) -> tuple[list[TrunkState], list[str]]:
    """Load each trunk's parent, subports and NB rows, skipping ovn-owned trunks."""
    states: list[TrunkState] = []
    skipped: list[str] = []
    for trunk in trunks:
        parent = conn.network.get_port(_value(trunk, "port_id"))
        if _value(parent, "binding_vnic_type") != BAREMETAL_VNIC_TYPE:
            skipped.append(
                f"trunk {_label(trunk)}: parent port is not baremetal, "
                "so ml2/ovn still owns this trunk"
            )
            continue
        subports = [
            conn.network.get_port(subport["port_id"])
            for subport in _value(trunk, "sub_ports") or []
        ]
        port_ids = [_value(port, "id") for port in subports]
        states.append(
            TrunkState(trunk, parent, subports, _lsp_rows(conn_ctx, port_ids))
        )
    return states, skipped


def _audit_trunk(state: TrunkState) -> list[Finding]:
    findings: list[Finding] = []
    bound = _parent_is_bound(state.parent)
    expected_status = "ACTIVE" if bound else "DOWN"
    status = _value(state.trunk, "status")
    _check(
        findings,
        status == expected_status,
        "trunk status",
        expected_status,
        f"expected {expected_status} for a "
        f"{'bound' if bound else 'unbound'} parent, found {status}; a trunk "
        "last touched before the status fix corrects itself on its next "
        "subport change",
    )
    for port in state.subports:
        port_id = _value(port, "id")
        label = f"subport {port_id}"
        stale_keys = _stale_profile_keys(port)
        _check(
            findings,
            not stale_keys,
            f"{label}: binding profile",
            "no ml2/ovn trunk keys",
            f"stale ml2/ovn keys: {', '.join(stale_keys)}",
        )
        lsp = state.lsps.get(port_id)
        if lsp is None:
            findings.append(
                Finding("SKIP", f"{label}: LSP", "no Logical_Switch_Port in the NB")
            )
        else:
            stale_columns = _stale_lsp_columns(lsp)
            _check(
                findings,
                not stale_columns,
                f"{label}: LSP columns",
                "parent_name and tag_request unset",
                f"still set: {', '.join(stale_columns)}",
            )
        owner = _value(port, "device_owner")
        _check(
            findings,
            owner == SUBPORT_DEVICE_OWNER,
            f"{label}: device_owner",
            SUBPORT_DEVICE_OWNER,
            f"expected {SUBPORT_DEVICE_OWNER}, found {owner or '(empty)'}",
        )
    return findings


def _repair_operations(state: TrunkState) -> list[SubportRepair]:
    operations: list[SubportRepair] = []
    for port in state.subports:
        port_id = _value(port, "id")
        updates: dict[str, Any] = {}
        changes: list[str] = []

        stale_keys = _stale_profile_keys(port)
        if stale_keys:
            profile = _value(port, "binding_profile") or {}
            updates["binding_profile"] = {
                key: value
                for key, value in profile.items()
                if key not in STALE_PROFILE_KEYS
            }
            changes.append(f"binding profile: drop {', '.join(stale_keys)}")
        owner = _value(port, "device_owner")
        if owner != SUBPORT_DEVICE_OWNER:
            updates["device_owner"] = SUBPORT_DEVICE_OWNER
            changes.append(
                f"device_owner: {owner or '(empty)'} -> {SUBPORT_DEVICE_OWNER}"
            )
        clear_columns = _stale_lsp_columns(state.lsps.get(port_id))
        if clear_columns:
            changes.append(f"LSP: clear {', '.join(clear_columns)}")

        if updates or clear_columns:
            operations.append(
                SubportRepair(port_id, updates, clear_columns, tuple(changes))
            )
    return operations


def _clear_stale_lsp_columns(
    conn_ctx: ConnectionContext, port_ids: list[str]
) -> list[str]:
    """Clear whatever ml2/ovn's own rewrite left behind. Returns what was cleared."""
    args: list[str] = []
    cleared: list[str] = []
    for port_id, row in _lsp_rows(conn_ctx, port_ids).items():
        for column in _stale_lsp_columns(row):
            args += ["--", "clear", "Logical_Switch_Port", port_id, column]
            cleared.append(f"{port_id}: {column}")
    if args:
        ovn.nbctl_raw(conn_ctx, args)
    return cleared


@app.command("audit")
def audit(
    ctx: typer.Context,
    name_or_id: str = typer.Argument(
        None, help="Neutron trunk name or ID (default: every baremetal trunk)"
    ),
) -> None:
    """Report ml2/ovn trunk state left on baremetal trunks and their subports."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx, include_openstack=True)
    try:
        conn = osclient.get_connection(conn_ctx.os_cloud)
        states, skipped = _load_states(
            conn, conn_ctx, _resolve_trunks(conn, name_or_id)
        )
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    print()
    for reason in skipped:
        print(f"SKIP  {reason}")
    if not states:
        print("(no baremetal trunks found)")
        return

    failed = False
    for state in states:
        print(f"\nTrunk {_label(state.trunk)}")
        parent_state = "bound" if _parent_is_bound(state.parent) else "unbound"
        print(f"Parent port: {_value(state.parent, 'id')} (baremetal, {parent_state})")
        findings = _audit_trunk(state)
        for finding in findings:
            print(f"  {finding.status:<4}  {finding.check}: {finding.detail}")
        failed = failed or any(finding.status == "FAIL" for finding in findings)

    if failed:
        raise typer.Exit(1)


@app.command("repair")
def repair(
    ctx: typer.Context,
    name_or_id: str = typer.Argument(
        None, help="Neutron trunk name or ID (default: every baremetal trunk)"
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the displayed plan; without this flag no changes are made",
    ),
) -> None:
    """Strip ml2/ovn's leftover parent_name/tag from baremetal trunk subports."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx, include_openstack=True)
    try:
        conn = osclient.get_connection(conn_ctx.os_cloud)
        trunks = _resolve_trunks(conn, name_or_id)
        states, skipped = _load_states(conn, conn_ctx, trunks)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    print()
    for reason in skipped:
        print(f"SKIP  {reason}")
    print(
        "Repair scope: subport binding profiles, their trunk device_owner, and "
        "the LSP columns derived from them"
    )
    plan = [(state, _repair_operations(state)) for state in states]
    for state, operations in plan:
        if not operations:
            continue
        print(f"\nTrunk {_label(state.trunk)}")
        for operation in operations:
            print(f"  subport {operation.port_id}")
            for change in operation.changes:
                print(f"    {change}")

    total = sum(len(operations) for _, operations in plan)
    if not total:
        print("\nNo leftover ml2/ovn trunk state found.")
        return
    if not apply:
        print("\nDry run only. Re-run with --apply to make these changes.")
        return

    try:
        for _, operations in plan:
            for operation in operations:
                if operation.port_updates:
                    conn.network.update_port(
                        operation.port_id, **operation.port_updates
                    )
        # ml2/ovn rewrites the LSP from the binding profile we just changed, so
        # only clear directly what it left behind.
        port_ids = [
            operation.port_id for _, operations in plan for operation in operations
        ]
        cleared = _clear_stale_lsp_columns(conn_ctx, port_ids)
        refreshed, _ = _load_states(conn, conn_ctx, trunks)
        remaining = [
            operation for state in refreshed for operation in _repair_operations(state)
        ]
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    for entry in cleared:
        print(f"  cleared in the NB directly: {entry}")
    if remaining:
        typer.echo("ERROR: repair verification failed", err=True)
        for operation in remaining:
            typer.echo(
                f"  {operation.port_id}: {', '.join(operation.changes)}", err=True
            )
        raise typer.Exit(1)
    print(f"\nRepaired {total} subport(s); verification passed.")
