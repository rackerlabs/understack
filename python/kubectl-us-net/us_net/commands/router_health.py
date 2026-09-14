"""Audit and narrowly repair Neutron router realization state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import typer

from us_net import osclient
from us_net import ovn
from us_net.commands.router_common import GATEWAY_DEVICE_OWNER
from us_net.commands.router_common import NEUTRON_PREFIX
from us_net.commands.router_common import ROUTER_INTERFACE_DEVICE_OWNERS
from us_net.commands.router_common import rows_by_uuid
from us_net.connection import ConnectionContext
from us_net.connection import print_connection_banner

OVN_NETWORK_ID_EXT_ID_KEY = "neutron:network_id"
OVN_ROUTER_ID_EXT_ID_KEY = "neutron:router_id"
HA_CHASSIS_GROUP_HIGHEST_PRIORITY = 32767


@dataclass(frozen=True)
class Finding:
    """One audit assertion."""

    status: str
    check: str
    detail: str


@dataclass
class OvnInventory:
    """Relevant NB state, loaded once per command."""

    routers: dict[str, dict]
    router_ports: dict[str, dict]
    switch_ports: dict[str, dict]
    switch_port_parents: dict[str, list[str]]


@dataclass
class RouterHaChassisInventory:
    """Router-owned HA chassis groups, their members, and SB liveness."""

    groups: list[dict]
    members_by_uuid: dict[str, dict]
    live_chassis_names: set[str]


@dataclass(frozen=True)
class RepairOperation:
    """A single safe Logical_Switch_Port update."""

    port_id: str
    assignments: tuple[str, ...]
    changes: tuple[str, ...]


@dataclass(frozen=True)
class HaChassisGroupRepairOperation:
    """A safe repopulation of one router-owned per-network HA chassis group."""

    group_uuid: str
    group_name: str
    target_chassis: str
    remove_member_uuids: tuple[str, ...]


def _value(resource: Any, key: str, default=None):
    """Read an SDK resource or dict without depending on its concrete type."""
    value = getattr(resource, key, None)
    if value is not None:
        return value
    getter = getattr(resource, "get", None)
    return getter(key, default) if getter else default


def _find_rows(
    conn_ctx: ConnectionContext, table: str, column: str, values: set[str]
) -> list[dict]:
    """Find a small set of rows and de-duplicate overlapping queries."""
    if not values:
        return []
    if column in {"_uuid", "name"}:
        return ovn.nbctl_list_records(conn_ctx, table, sorted(values))
    rows: dict[str, dict] = {}
    for value in sorted(values):
        for row in ovn.nbctl_find(conn_ctx, table, f"{column}={value}"):
            rows[row.get("_uuid") or row.get("name", "")] = row
    return list(rows.values())


def _load_inventory(
    conn_ctx: ConnectionContext,
    router_id: str,
    ports: list[Any],
    additional_lsp_names: set[str] | None = None,
) -> OvnInventory:
    """Load router-scoped rows while retaining exact switch membership."""
    lr_name = f"{NEUTRON_PREFIX}{router_id}"
    lr_rows = ovn.nbctl_find(conn_ctx, "Logical_Router", f"name={lr_name}")
    routers = {row.get("name", ""): row for row in lr_rows}

    attached_lrp_uuids = {
        uuid for lr in lr_rows for uuid in ovn.as_list(lr.get("ports"))
    }
    lrp_rows = _find_rows(conn_ctx, "Logical_Router_Port", "_uuid", attached_lrp_uuids)
    expected_lrp_names = {f"lrp-{_value(port, 'id')}" for port in ports}
    found_lrp_names = {row.get("name", "") for row in lrp_rows}
    lrp_rows.extend(
        _find_rows(
            conn_ctx,
            "Logical_Router_Port",
            "name",
            expected_lrp_names - found_lrp_names,
        )
    )
    router_ports = {row.get("name", ""): row for row in lrp_rows}

    lsp_names = {_value(port, "id") for port in ports if _value(port, "id") is not None}
    lsp_names.update(additional_lsp_names or set())
    lsp_names.update(
        name.removeprefix("lrp-") for name in router_ports if name.startswith("lrp-")
    )
    lsp_rows = _find_rows(conn_ctx, "Logical_Switch_Port", "name", lsp_names)
    switch_ports = {row.get("name", ""): row for row in lsp_rows}

    switch_port_parents: dict[str, list[str]] = {}
    # A complete switch membership map is required to prove an LSP is attached
    # to exactly one switch, rather than merely finding it on the expected one.
    for switch in ovn.nbctl_list(conn_ctx, "Logical_Switch"):
        for port_uuid in ovn.as_list(switch.get("ports")):
            switch_port_parents.setdefault(port_uuid, []).append(switch.get("name", ""))
    return OvnInventory(
        routers=routers,
        router_ports=router_ports,
        switch_ports=switch_ports,
        switch_port_parents=switch_port_parents,
    )


def _load_router_ha_chassis_inventory(
    conn_ctx: ConnectionContext,
    router_id: str,
    candidate_chassis_names: set[str] | None = None,
) -> RouterHaChassisInventory:
    """Load router-owned HA group members and relevant chassis liveness."""
    escaped_key = OVN_ROUTER_ID_EXT_ID_KEY.replace(":", r"\:")
    groups = ovn.nbctl_find(
        conn_ctx,
        "HA_Chassis_Group",
        f"external_ids:{escaped_key}={router_id}",
    )
    member_uuids = {
        member_uuid
        for group in groups
        for member_uuid in ovn.as_list(group.get("ha_chassis"))
    }
    members = (
        ovn.nbctl_list_records(conn_ctx, "HA_Chassis", sorted(member_uuids))
        if member_uuids
        else []
    )
    members_by_uuid = {member["_uuid"]: member for member in members}
    chassis_names = {
        member.get("chassis_name", "")
        for member in members
        if member.get("chassis_name")
    }
    chassis_names.update(candidate_chassis_names or set())
    live_chassis_names = (
        {
            row.get("name", "")
            for row in ovn.sbctl_list(conn_ctx, "Chassis")
            if row.get("name") in chassis_names
        }
        if chassis_names
        else set()
    )
    return RouterHaChassisInventory(groups, members_by_uuid, live_chassis_names)


def _group_members(
    group: dict, inventory: RouterHaChassisInventory
) -> tuple[set[str], list[dict], list[str]]:
    member_uuids = set(ovn.as_list(group.get("ha_chassis")))
    members = [
        inventory.members_by_uuid[member_uuid]
        for member_uuid in member_uuids
        if member_uuid in inventory.members_by_uuid
    ]
    live_names = sorted(
        {
            member.get("chassis_name", "")
            for member in members
            if member.get("chassis_name") in inventory.live_chassis_names
        }
    )
    return member_uuids, members, live_names


def _audit_network_ha_chassis_groups(
    inventory: RouterHaChassisInventory,
) -> list[Finding]:
    """Check router-owned per-network HA groups have a live member."""
    findings: list[Finding] = []
    for group in inventory.groups:
        external_ids = group.get("external_ids") or {}
        network_id = external_ids.get(OVN_NETWORK_ID_EXT_ID_KEY)
        if not network_id:
            continue

        member_uuids, members, live_names = _group_members(group, inventory)
        resolved_uuids = {member.get("_uuid") for member in members}
        missing_uuids = sorted(member_uuids - resolved_uuids)
        stale_names = sorted(
            member.get("chassis_name") or "(unnamed)"
            for member in members
            if member.get("chassis_name") not in inventory.live_chassis_names
        )

        group_name = group.get("name") or f"neutron-{network_id}"
        if live_names:
            findings.append(
                Finding(
                    "PASS",
                    f"per-network HA chassis group {group_name}",
                    f"live members: {', '.join(sorted(live_names))}",
                )
            )
            continue

        details: list[str] = []
        if not member_uuids:
            details.append("no HA_Chassis members")
        if stale_names:
            details.append(f"non-live members: {', '.join(sorted(stale_names))}")
        if missing_uuids:
            details.append(f"missing HA_Chassis rows: {', '.join(missing_uuids)}")
        findings.append(
            Finding(
                "FAIL",
                f"per-network HA chassis group {group_name}",
                "; ".join(details) + "; repopulation required",
            )
        )
    return findings


def _ha_chassis_repopulation_target(
    router,
    inventory: OvnInventory,
    ha_inventory: RouterHaChassisInventory,
) -> tuple[str | None, str | None]:
    """Resolve the one live chassis safe for per-network group repair."""
    router_id = _value(router, "id")
    lr = inventory.routers.get(f"{NEUTRON_PREFIX}{router_id}")
    if lr is None:
        return None, f"logical router {NEUTRON_PREFIX}{router_id} is missing"

    centralized_chassis = (lr.get("options") or {}).get("chassis")
    if centralized_chassis:
        if centralized_chassis in ha_inventory.live_chassis_names:
            return centralized_chassis, None
        return (
            None,
            f"logical router options:chassis={centralized_chassis} is not live",
        )

    router_group_name = f"{NEUTRON_PREFIX}{router_id}"
    router_group = next(
        (
            group
            for group in ha_inventory.groups
            if group.get("name") == router_group_name
        ),
        None,
    )
    if router_group is None:
        return None, f"router HA chassis group {router_group_name} is missing"

    live_names = _group_members(router_group, ha_inventory)[2]
    if len(live_names) == 1:
        return live_names[0], None
    return (
        None,
        f"router HA chassis group {router_group_name} resolves to "
        f"{len(live_names)} live chassis; expected exactly one",
    )


def _audit_ha_chassis_repopulation_source(
    router,
    inventory: OvnInventory,
    ha_inventory: RouterHaChassisInventory,
) -> list[Finding]:
    """Report whether failed per-network groups have a repair source."""
    needs_repopulation = any(
        (group.get("external_ids") or {}).get(OVN_NETWORK_ID_EXT_ID_KEY)
        and not _group_members(group, ha_inventory)[2]
        for group in ha_inventory.groups
    )
    if not needs_repopulation:
        return []

    target, error = _ha_chassis_repopulation_target(router, inventory, ha_inventory)
    return [
        Finding(
            "PASS" if target else "FAIL",
            "HA chassis repopulation source",
            f"live chassis: {target}" if target else error or "unavailable",
        )
    ]


def _binding_host(port) -> str:
    return _value(port, "binding_host_id") or _value(port, "binding:host_id") or ""


def _router_ports(conn, router_id: str) -> list[Any]:
    return [
        port
        for port in conn.network.ports(device_id=router_id)
        if _value(port, "device_owner")
        in {GATEWAY_DEVICE_OWNER, *ROUTER_INTERFACE_DEVICE_OWNERS}
    ]


def _network_uplink_ports(conn, ports: list[Any]) -> dict[str, list[Any]]:
    """Return UnderStack's shared uplink port intent per router network."""
    uplinks: dict[str, list[Any]] = {}
    network_ids = {
        _value(port, "network_id") for port in ports if _value(port, "network_id")
    }
    for network_id in sorted(network_ids):
        uplinks[network_id] = [
            port
            for port in conn.network.ports(network_id=network_id)
            if (_value(port, "name") or "").startswith("uplink-")
        ]
    return uplinks


def _expected_switch(port, lsp: dict | None) -> str:
    switch_id = _value(port, "network_id")
    if _value(port, "device_owner") != GATEWAY_DEVICE_OWNER:
        # Router interfaces are not currently host-bound, so ML2/OVN cannot
        # segment-place them today. Honor a future segment stamp defensively.
        segment_id = ((lsp or {}).get("external_ids") or {}).get(
            "neutron:port_segment_id"
        )
        switch_id = segment_id or switch_id
    return f"{NEUTRON_PREFIX}{switch_id}"


def _requested_chassis_matches(requested: str, host: str) -> bool:
    requested_hosts = {item.strip() for item in requested.split(",") if item.strip()}
    return host in requested_hosts if host else not requested_hosts


def _attached_names(
    parent: dict | None, column: str, rows: dict[str, dict]
) -> set[str]:
    if not parent:
        return set()
    uuids = set(ovn.as_list(parent.get(column)))
    return {row.get("name", "") for row in rows_by_uuid(list(rows.values()), uuids)}


def _switches_for_lsp(lsp: dict | None, inventory: OvnInventory) -> list[str]:
    if not lsp:
        return []
    return inventory.switch_port_parents.get(lsp.get("_uuid"), [])


def _check(
    findings: list[Finding], condition: bool, name: str, good: str, bad: str
) -> None:
    findings.append(
        Finding("PASS" if condition else "FAIL", name, good if condition else bad)
    )


def _audit_native_router(
    router,
    ports: list[Any],
    inventory: OvnInventory,
    uplink_ports: dict[str, list[Any]],
) -> list[Finding]:
    findings: list[Finding] = []
    router_id = _value(router, "id")
    lr_name = f"{NEUTRON_PREFIX}{router_id}"
    lr = inventory.routers.get(lr_name)
    _check(
        findings,
        lr is not None,
        "logical router",
        lr_name,
        f"missing {lr_name}",
    )
    if lr is None:
        return findings

    attached_lrps = _attached_names(lr, "ports", inventory.router_ports)
    expected_lrps = {f"lrp-{_value(port, 'id')}" for port in ports}
    for lrp_name in sorted(attached_lrps - expected_lrps):
        findings.append(
            Finding(
                "FAIL",
                f"orphaned LRP {lrp_name}",
                "attached to the logical router without a Neutron router port",
            )
        )
        orphan_lsps = [
            lsp
            for lsp in inventory.switch_ports.values()
            if (lsp.get("options") or {}).get("router-port") == lrp_name
        ]
        for lsp in orphan_lsps:
            findings.append(
                Finding(
                    "FAIL",
                    f"orphaned peer LSP {lsp.get('name', '(unnamed)')}",
                    f"references attached {lrp_name} without a Neutron router port",
                )
            )

    audited_networks: set[str] = set()
    for port in sorted(
        ports,
        key=lambda item: (
            _value(item, "device_owner") != GATEWAY_DEVICE_OWNER,
            _value(item, "id"),
        ),
    ):
        port_id = _value(port, "id")
        owner = _value(port, "device_owner")
        role = "gateway" if owner == GATEWAY_DEVICE_OWNER else "internal"
        network_id = _value(port, "network_id")
        lrp_name = f"lrp-{port_id}"
        lrp = inventory.router_ports.get(lrp_name)
        _check(
            findings,
            lrp is not None and lrp_name in attached_lrps,
            f"{role} {port_id}: LRP attachment",
            f"{lrp_name} attached to {lr_name}",
            f"{lrp_name} missing or not attached to {lr_name}",
        )

        lsp = inventory.switch_ports.get(port_id)
        actual_switches = _switches_for_lsp(lsp, inventory)
        expected_switch = _expected_switch(port, lsp)
        _check(
            findings,
            lsp is not None and actual_switches == [expected_switch],
            f"{role} {port_id}: LSP attachment",
            f"attached to {expected_switch}",
            f"expected {expected_switch}, found {actual_switches or 'no attachment'}",
        )
        if lsp is None:
            if network_id not in audited_networks:
                findings.extend(
                    _audit_network_uplink(
                        role,
                        network_id,
                        uplink_ports.get(network_id, []),
                        inventory,
                    )
                )
                audited_networks.add(network_id)
            continue

        _check(
            findings,
            lsp.get("type") == "router",
            f"{role} {port_id}: LSP type",
            "router",
            f"expected router, found {lsp.get('type') or '(empty)'}",
        )
        addresses = ovn.as_list(lsp.get("addresses"))
        _check(
            findings,
            addresses == ["router"],
            f"{role} {port_id}: LSP addresses",
            "router",
            f"expected ['router'], found {addresses}",
        )
        options = lsp.get("options") or {}
        _check(
            findings,
            options.get("router-port") == lrp_name,
            f"{role} {port_id}: router-port option",
            lrp_name,
            f"expected {lrp_name}, found {options.get('router-port') or '(missing)'}",
        )
        if role == "gateway":
            _check(
                findings,
                options.get("nat-addresses") == "router",
                f"gateway {port_id}: nat-addresses option",
                "router",
                f"expected router, found {options.get('nat-addresses') or '(missing)'}",
            )
            _check(
                findings,
                options.get("exclude-lb-vips-from-garp") == "true",
                f"gateway {port_id}: exclude-lb-vips-from-garp option",
                "true",
                "expected true, found "
                f"{options.get('exclude-lb-vips-from-garp') or '(missing)'}",
            )

        requested = options.get("requested-chassis", "")
        host = _binding_host(port)
        _check(
            findings,
            _requested_chassis_matches(requested, host),
            f"{role} {port_id}: requested-chassis",
            requested or "not requested (port is not host-bound)",
            f"Neutron binding:host_id={host or '(empty)'}, "
            f"OVN requested-chassis={requested or '(empty)'}",
        )
        if network_id not in audited_networks:
            findings.extend(
                _audit_network_uplink(
                    role,
                    network_id,
                    uplink_ports.get(network_id, []),
                    inventory,
                )
            )
            audited_networks.add(network_id)
    return findings


def _audit_network_uplink(
    role: str,
    network_id: str,
    ports: list[Any],
    inventory: OvnInventory,
) -> list[Finding]:
    """Check one router network's shared uplink and localnet LSP."""
    findings: list[Finding] = []
    names = sorted(name for port in ports if (name := _value(port, "name")) is not None)
    count_ok = len(names) == 1
    _check(
        findings,
        count_ok,
        f"{role} network {network_id}: uplink port intent",
        names[0] if count_ok else "",
        f"expected exactly one uplink-* Neutron port, found {names or 'none'}",
    )
    for name in names:
        lsp = inventory.switch_ports.get(name)
        actual_switches = _switches_for_lsp(lsp, inventory)
        expected_switch = f"{NEUTRON_PREFIX}{network_id}"
        _check(
            findings,
            lsp is not None and actual_switches == [expected_switch],
            f"{role} uplink {name}: LSP attachment",
            f"attached to {expected_switch}",
            f"expected {expected_switch}, found {actual_switches or 'no attachment'}",
        )
        if lsp is None:
            continue
        _check(
            findings,
            lsp.get("type") == "localnet",
            f"{role} uplink {name}: LSP type",
            "localnet",
            f"expected localnet, found {lsp.get('type') or '(empty)'}",
        )
        addresses = ovn.as_list(lsp.get("addresses"))
        _check(
            findings,
            addresses == ["unknown"],
            f"{role} uplink {name}: LSP addresses",
            "unknown",
            f"expected ['unknown'], found {addresses}",
        )
        tags = ovn.as_list(lsp.get("tag"))
        _check(
            findings,
            len(tags) == 1,
            f"{role} uplink {name}: VLAN tag",
            str(tags[0]) if len(tags) == 1 else "",
            f"expected one VLAN tag, found {tags or 'none'}",
        )
    return findings


def _print_audit(router, findings: list[Finding]) -> None:
    print(f"\nRouter {_value(router, 'name') or '(unnamed)'} ({_value(router, 'id')})")
    print("Backend: native OVN")
    for finding in findings:
        print(f"  {finding.status:<4}  {finding.check}: {finding.detail}")


def audit(
    ctx: typer.Context,
    name_or_id: str = typer.Argument(..., help="Neutron router name or ID"),
) -> None:
    """Compare Neutron router intent with native OVN realization."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx, include_openstack=True)
    try:
        conn = osclient.get_connection(conn_ctx.os_cloud)
        router = osclient.resolve_router(conn, name_or_id)
        flavor_id = _value(router, "flavor_id")
        if flavor_id:
            print(
                f"\nRouter {_value(router, 'name') or '(unnamed)'} "
                f"({_value(router, 'id')})"
            )
            print(
                f"  SKIP  router has flavor {flavor_id}; "
                "only unflavored native OVN routers are supported"
            )
            return
        ports = _router_ports(conn, _value(router, "id"))
        uplink_ports = _network_uplink_ports(conn, ports)
        inventory = _load_inventory(
            conn_ctx,
            _value(router, "id"),
            ports,
            {
                name
                for network_ports in uplink_ports.values()
                for port in network_ports
                if (name := _value(port, "name"))
            },
        )
        findings = _audit_native_router(router, ports, inventory, uplink_ports)
        lr = inventory.routers.get(f"{NEUTRON_PREFIX}{_value(router, 'id')}")
        centralized_chassis = (lr.get("options") or {}).get("chassis") if lr else None
        ha_inventory = _load_router_ha_chassis_inventory(
            conn_ctx,
            _value(router, "id"),
            {centralized_chassis} if centralized_chassis else None,
        )
        findings.extend(_audit_network_ha_chassis_groups(ha_inventory))
        findings.extend(
            _audit_ha_chassis_repopulation_source(router, inventory, ha_inventory)
        )
        _print_audit(router, findings)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc
    else:
        if any(finding.status == "FAIL" for finding in findings):
            raise typer.Exit(1)


def _repair_operations(
    router,
    ports: list[Any],
    inventory: OvnInventory,
) -> tuple[list[RepairOperation], list[str]]:
    operations: list[RepairOperation] = []
    refused: list[str] = []
    router_id = _value(router, "id")
    lr_name = f"{NEUTRON_PREFIX}{router_id}"
    lr = inventory.routers.get(lr_name)
    if lr is None:
        return [], [f"logical router {lr_name} is missing"]
    attached_lrps = _attached_names(lr, "ports", inventory.router_ports)
    expected_lrps = {f"lrp-{_value(port, 'id')}" for port in ports}
    for lrp_name in sorted(attached_lrps - expected_lrps):
        refused.append(
            f"{lrp_name} is attached to {lr_name} without a Neutron router port"
        )

    for port in ports:
        owner = _value(port, "device_owner")
        port_id = _value(port, "id")
        lrp_name = f"lrp-{port_id}"
        lrp = inventory.router_ports.get(lrp_name)
        lsp = inventory.switch_ports.get(port_id)
        switches = _switches_for_lsp(lsp, inventory)
        expected_switch = _expected_switch(port, lsp)
        if lrp is None or lrp_name not in attached_lrps:
            refused.append(
                f"{port_id}: {lrp_name} is missing or not attached to {lr_name}"
            )
            continue
        if lsp is None or switches != [expected_switch]:
            refused.append(
                f"{port_id}: LSP attachment is invalid: "
                f"expected {expected_switch}, found {switches or 'no attachment'}"
            )
            continue

        assignments: list[str] = []
        changes: list[str] = []
        if lsp.get("type") != "router":
            assignments.append("type=router")
            changes.append(f"type: {lsp.get('type') or '(empty)'} -> router")
        addresses = ovn.as_list(lsp.get("addresses"))
        if addresses != ["router"]:
            assignments.append("addresses=router")
            changes.append(f"addresses: {addresses} -> ['router']")
        options = lsp.get("options") or {}
        required_options = {"router-port": lrp_name}
        if owner == GATEWAY_DEVICE_OWNER:
            required_options.update(
                {
                    "nat-addresses": "router",
                    "exclude-lb-vips-from-garp": "true",
                }
            )
        for key, expected in required_options.items():
            if options.get(key) != expected:
                assignments.append(f"options:{key}={expected}")
                changes.append(
                    f"options:{key}: {options.get(key) or '(missing)'} -> {expected}"
                )
        if assignments:
            operations.append(
                RepairOperation(port_id, tuple(assignments), tuple(changes))
            )
    return operations, refused


def _ha_chassis_group_repair_operations(
    router,
    inventory: OvnInventory,
    ha_inventory: RouterHaChassisInventory,
) -> tuple[list[HaChassisGroupRepairOperation], list[str]]:
    """Plan repopulation of empty or stale-only per-network HA groups."""
    router_id = _value(router, "id")
    lr_name = f"{NEUTRON_PREFIX}{router_id}"
    lr = inventory.routers.get(lr_name)
    if lr is None:
        return [], []

    network_groups = [
        group
        for group in ha_inventory.groups
        if (group.get("external_ids") or {}).get(OVN_NETWORK_ID_EXT_ID_KEY)
    ]
    groups_needing_repopulation = [
        group for group in network_groups if not _group_members(group, ha_inventory)[2]
    ]
    if not groups_needing_repopulation:
        return [], []

    target_chassis, target_error = _ha_chassis_repopulation_target(
        router, inventory, ha_inventory
    )

    operations: list[HaChassisGroupRepairOperation] = []
    refused: list[str] = []
    for group in groups_needing_repopulation:
        group_name = group.get("name") or "(unnamed)"
        group_uuid = group.get("_uuid")
        if not group_uuid:
            refused.append(f"{group_name}: HA chassis group UUID is missing")
        elif target_chassis is None:
            refused.append(f"{group_name}: {target_error}")
        else:
            operations.append(
                HaChassisGroupRepairOperation(
                    group_uuid=group_uuid,
                    group_name=group_name,
                    target_chassis=target_chassis,
                    remove_member_uuids=tuple(
                        sorted(ovn.as_list(group.get("ha_chassis")))
                    ),
                )
            )
    return operations, refused


def _verify_ha_chassis_group_repairs(
    operations: list[HaChassisGroupRepairOperation],
    inventory: RouterHaChassisInventory,
) -> list[str]:
    """Verify each applied HA chassis group operation against its plan."""
    errors: list[str] = []
    groups_by_uuid = {group.get("_uuid"): group for group in inventory.groups}
    for operation in operations:
        group = groups_by_uuid.get(operation.group_uuid)
        if group is None:
            errors.append(f"{operation.group_name}: HA chassis group is missing")
            continue

        member_uuids = set(ovn.as_list(group.get("ha_chassis")))
        stale_uuids = sorted(member_uuids.intersection(operation.remove_member_uuids))
        if stale_uuids:
            errors.append(
                f"{operation.group_name}: removed HA_Chassis references remain: "
                f"{', '.join(stale_uuids)}"
            )

        target_members = [
            inventory.members_by_uuid[member_uuid]
            for member_uuid in member_uuids
            if member_uuid in inventory.members_by_uuid
            and inventory.members_by_uuid[member_uuid].get("chassis_name")
            == operation.target_chassis
        ]
        if not target_members:
            errors.append(
                f"{operation.group_name}: target chassis "
                f"{operation.target_chassis} is not a member"
            )
            continue
        if not any(
            member.get("priority") == HA_CHASSIS_GROUP_HIGHEST_PRIORITY
            for member in target_members
        ):
            priorities = sorted(
                str(member.get("priority", "(missing)")) for member in target_members
            )
            errors.append(
                f"{operation.group_name}: target chassis {operation.target_chassis} "
                f"has priority {', '.join(priorities)}, expected "
                f"{HA_CHASSIS_GROUP_HIGHEST_PRIORITY}"
            )
    return errors


def repair(
    ctx: typer.Context,
    name_or_id: str = typer.Argument(..., help="Neutron router name or ID"),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Apply the displayed plan; without this flag no changes are made",
    ),
) -> None:
    """Repair safe native-OVN router LSP and HA chassis group state."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx, include_openstack=True)
    try:
        conn = osclient.get_connection(conn_ctx.os_cloud)
        router = osclient.resolve_router(conn, name_or_id)
        flavor_id = _value(router, "flavor_id")
        if flavor_id:
            typer.echo(
                f"REFUSED: router has flavor {flavor_id}; this repair only "
                "supports unflavored native OVN routers",
                err=True,
            )
            raise typer.Exit(2)
        ports = _router_ports(conn, _value(router, "id"))
        inventory = _load_inventory(conn_ctx, _value(router, "id"), ports)
        operations, lsp_refused = _repair_operations(router, ports, inventory)
        lr = inventory.routers.get(f"{NEUTRON_PREFIX}{_value(router, 'id')}")
        centralized_chassis = (lr.get("options") or {}).get("chassis") if lr else None
        ha_inventory = _load_router_ha_chassis_inventory(
            conn_ctx,
            _value(router, "id"),
            {centralized_chassis} if centralized_chassis else None,
        )
        ha_group_operations, ha_refused = _ha_chassis_group_repair_operations(
            router,
            inventory,
            ha_inventory,
        )
    except typer.Exit:
        raise
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    print(f"\nRouter {_value(router, 'name') or '(unnamed)'} ({_value(router, 'id')})")
    print(
        "Repair scope: attached router peer LSP fields and unambiguous "
        "per-network HA chassis group repopulation"
    )
    for reason in lsp_refused:
        print(f"  REFUSED LSP repair  {reason}")
    for reason in ha_refused:
        print(f"  REFUSED HA chassis group repair  {reason}")

    allowed_operations = [] if lsp_refused else operations
    allowed_ha_group_operations = [] if ha_refused else ha_group_operations
    for operation in allowed_operations:
        print(f"  LSP {operation.port_id}")
        for change in operation.changes:
            print(f"    {change}")
    for operation in allowed_ha_group_operations:
        print(f"  HA chassis group {operation.group_name}")
        if operation.remove_member_uuids:
            print(
                "    remove non-live members: "
                f"{', '.join(operation.remove_member_uuids)}"
            )
        print(f"    repopulate with live chassis: {operation.target_chassis}")

    has_refusals = bool(lsp_refused or ha_refused)
    if not allowed_operations and not allowed_ha_group_operations:
        if not has_refusals:
            print("\nNo repairable differences found.")
            return
        typer.echo(
            "\nNo changes made: all required repair domains are either clean "
            "or refused.",
            err=True,
        )
        raise typer.Exit(2)
    if not apply:
        print("\nDry run only. Re-run with --apply to make these changes.")
        if has_refusals:
            raise typer.Exit(2)
        return

    args: list[str] = []
    for operation in allowed_operations:
        args.extend(
            [
                "--",
                "set",
                "Logical_Switch_Port",
                operation.port_id,
                *operation.assignments,
            ]
        )
    for index, operation in enumerate(allowed_ha_group_operations):
        for member_uuid in operation.remove_member_uuids:
            args.extend(
                [
                    "--",
                    "--if-exists",
                    "remove",
                    "HA_Chassis_Group",
                    operation.group_uuid,
                    "ha_chassis",
                    member_uuid,
                ]
            )
        row_id = f"@ha_chassis_{index}"
        args.extend(
            [
                "--",
                f"--id={row_id}",
                "create",
                "HA_Chassis",
                f"chassis_name={operation.target_chassis}",
                f"priority={HA_CHASSIS_GROUP_HIGHEST_PRIORITY}",
                "--",
                "add",
                "HA_Chassis_Group",
                operation.group_uuid,
                "ha_chassis",
                row_id,
            ]
        )
    ovn.nbctl_raw(conn_ctx, args)

    refreshed = _load_inventory(conn_ctx, _value(router, "id"), ports)
    remaining: list[RepairOperation] = []
    structural: list[str] = []
    if allowed_operations:
        remaining, structural = _repair_operations(router, ports, refreshed)
    ha_verification_errors: list[str] = []
    if allowed_ha_group_operations:
        refreshed_lr = refreshed.routers.get(f"{NEUTRON_PREFIX}{_value(router, 'id')}")
        refreshed_chassis = (
            (refreshed_lr.get("options") or {}).get("chassis") if refreshed_lr else None
        )
        refreshed_ha = _load_router_ha_chassis_inventory(
            conn_ctx,
            _value(router, "id"),
            {refreshed_chassis} if refreshed_chassis else None,
        )
        ha_verification_errors = _verify_ha_chassis_group_repairs(
            allowed_ha_group_operations,
            refreshed_ha,
        )
    if structural or remaining or ha_verification_errors:
        typer.echo("ERROR: repair verification failed", err=True)
        for reason in structural:
            typer.echo(f"  {reason}", err=True)
        for operation in remaining:
            typer.echo(
                f"  {operation.port_id}: {', '.join(operation.changes)}", err=True
            )
        for reason in ha_verification_errors:
            typer.echo(f"  {reason}", err=True)
        raise typer.Exit(1)
    print(
        f"\nApplied {len(allowed_operations)} LSP repair(s) and "
        f"{len(allowed_ha_group_operations)} HA chassis group repair(s); "
        "verification passed."
    )
    if has_refusals:
        typer.echo(
            "Some repair domains remain refused and require manual investigation.",
            err=True,
        )
        raise typer.Exit(2)


def register(app: typer.Typer) -> None:
    """Register health commands on the router command group."""
    app.command("audit")(audit)
    app.command("repair")(repair)
