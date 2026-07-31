"""`router show`/`router list`: cross-check Neutron routers against OVN state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import typer
from openstack import exceptions as os_exc

from us_net import osclient
from us_net import ovn
from us_net.connection import ConnectionContext
from us_net.connection import print_connection_banner

app = typer.Typer(no_args_is_help=True, help="Inspect a Neutron router's OVN state.")

NEUTRON_PREFIX = "neutron-"

GATEWAY_DEVICE_OWNER = "network:router_gateway"
INTERFACE_DEVICE_OWNER = "network:router_interface"


def _lrp_role(
    lrp_name: str, gateway_port_id: str | None, interface_port_ids: set[str]
) -> str:
    port_id = lrp_name.removeprefix("lrp-")
    if gateway_port_id and port_id == gateway_port_id:
        return "gateway"
    if port_id in interface_port_ids:
        return "internal"
    return "unknown"


def _rows_by_uuid(rows: list[dict], uuids: set[str]) -> list[dict]:
    """Filter a full OVN table dump down to rows referenced by a parent's uuid set."""
    return [row for row in rows if row.get("_uuid") in uuids]


def _chassis_physical_networks(chassis_row: dict | None) -> str:
    """Physical networks a chassis is wired for, via its ovn-bridge-mappings."""
    if chassis_row is None:
        return "(chassis not in SB)"
    mappings = (chassis_row.get("other_config") or {}).get("ovn-bridge-mappings")
    if not mappings:
        return "(no ovn-bridge-mappings configured)"
    return ", ".join(pair.split(":", 1)[0] for pair in mappings.split(",") if pair)


def _resolve_nat_port(conn, nat_row: dict) -> tuple[str | None, Any | None]:
    """Resolve the OpenStack port a NAT rule is bound to, if any.

    Prefers external_ids["neutron:fip_port_id"] (populated by neutron for
    floating-IP dnat_and_snat rules), then the logical_port column, then
    falls back to matching logical_ip against a port's fixed IPs -- only
    for single-host IPs, never for whole-subnet snat rules.
    """
    external_ids = nat_row.get("external_ids") or {}
    port_id = (
        external_ids.get("neutron:fip_port_id") or nat_row.get("logical_port") or None
    )
    if port_id:
        try:
            return port_id, conn.network.get_port(port_id)
        except os_exc.ResourceNotFound:
            return port_id, None

    logical_ip = nat_row.get("logical_ip")
    if logical_ip and "/" not in logical_ip:
        matches = list(conn.network.ports(fixed_ips=f"ip_address={logical_ip}"))
        if matches:
            return matches[0].id, matches[0]
    return None, None


def _describe_port_owner(conn, port) -> str:
    """Describe what a port is bound to: a server, or another device owner."""
    device_owner = getattr(port, "device_owner", None)
    device_id = getattr(port, "device_id", None)
    if device_owner and device_owner.startswith("compute:") and device_id:
        try:
            server = conn.compute.get_server(device_id)
            return f"server {device_id} ({server.name})"
        except Exception:
            return f"server {device_id}"
    if device_owner:
        return f"device_owner={device_owner}"
    return "unbound"


def _find_lsp(lsp_by_name: dict[str, dict], port_id: str) -> dict | None:
    """The OVN Logical_Switch_Port for a Neutron port, if it has one."""
    return lsp_by_name.get(port_id)


def _describe_lsp(lsp_row: dict | None) -> str:
    """Summarize an OVN Logical_Switch_Port row for cross-checking against Neutron."""
    if lsp_row is None:
        return "NOT FOUND (dangling?)"
    lsp_type = lsp_row.get("type") or "(normal)"
    addresses = ", ".join(ovn.as_list(lsp_row.get("addresses"))) or "(none)"
    up = "up" if lsp_row.get("up") else "down"
    return f"type={lsp_type}, {up}, addresses={addresses}"


def _describe_chassis_refs(
    chassis_uuids: list[str],
    chassis_rows: dict[str, dict],
    sb_chassis_by_name: dict[str, dict],
) -> str:
    """Format HA_Chassis/Gateway_Chassis rows, highest priority first.

    Both tables share the same chassis_name/priority shape, and priority
    order is OVN's actual failover preference.
    """
    rows = [chassis_rows[uuid] for uuid in chassis_uuids if uuid in chassis_rows]
    rows.sort(key=lambda row: row["priority"], reverse=True)
    chassis_descr = []
    for row in rows:
        chassis_name = row["chassis_name"]
        sb_row = sb_chassis_by_name.get(chassis_name)
        live = "alive" if sb_row is not None else "DEAD"
        physnets = _chassis_physical_networks(sb_row)
        chassis_descr.append(
            f"{chassis_name} (priority={row['priority']}, {live}, physnets={physnets})"
        )
    return "; ".join(chassis_descr) or "(empty)"


@dataclass
class ChassisTables:
    """OVN chassis-related tables, fetched once per `show()` invocation.

    Bundled into one object rather than passed as separate same-shaped
    dict[str, dict] parameters -- those couldn't be told apart by a type
    checker, so a transposed argument would silently look up the wrong
    table instead of raising.
    """

    hcg_rows: dict[str, dict]
    ha_chassis_rows: dict[str, dict]
    gateway_chassis_rows: dict[str, dict]
    sb_chassis_by_name: dict[str, dict]


def _describe_hcg(hcg_uuid: str | None, tables: ChassisTables) -> str:
    """Resolve an ha_chassis_group uuid into a human-readable chassis summary."""
    if not hcg_uuid:
        return "NOT LINKED"
    hcg = tables.hcg_rows.get(hcg_uuid)
    if hcg is None:
        return f"{hcg_uuid} (row not found!)"
    chassis_summary = _describe_chassis_refs(
        ovn.as_list(hcg.get("ha_chassis")),
        tables.ha_chassis_rows,
        tables.sb_chassis_by_name,
    )
    return f"{hcg['name']} -> {chassis_summary}"


def _localnet_tags(
    conn_ctx: ConnectionContext,
    switch_name: str | None,
    all_lsp_rows: list[dict],
    switch_row_cache: dict[str, dict | None],
) -> str:
    """VLAN tag(s) of a network's localnet/uplink port(s), via its OVN Logical_Switch.

    A network can have more than one (e.g. one per leaf-switch-pair segment).
    `all_lsp_rows` is the whole fleet's Logical_Switch_Port table, fetched
    once by the caller rather than per port. `switch_row_cache` memoizes the
    (cheap, scoped) Logical_Switch lookup across ports that share a network.
    """
    if not switch_name:
        return "(unknown network)"
    if switch_name not in switch_row_cache:
        rows = ovn.nbctl_find(conn_ctx, "Logical_Switch", f"name={switch_name}")
        switch_row_cache[switch_name] = rows[0] if rows else None
    switch_row = switch_row_cache[switch_name]
    if switch_row is None:
        return "(switch not found)"
    lsp_uuids = set(ovn.as_list(switch_row.get("ports")))
    candidate_lsps = _rows_by_uuid(all_lsp_rows, lsp_uuids)
    tags = [
        tag
        for lsp in candidate_lsps
        if lsp.get("type") == "localnet"
        for tag in ovn.as_list(lsp.get("tag"))
    ]
    return ", ".join(str(tag) for tag in tags) if tags else "(no localnet port)"


@app.command("show")
def show(
    ctx: typer.Context,
    name_or_id: str = typer.Argument(..., help="Neutron router name or ID"),
    flows: bool = typer.Option(
        False,
        "--flows",
        help="Also dump southbound logical flows for this router (can be large)",
    ),
) -> None:
    """Show a router's gateway/internal IPs, HCG state, NAT rules, and SB flows."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx, include_openstack=True)

    try:
        conn = osclient.get_connection(conn_ctx.os_cloud)
        router = osclient.resolve_router(conn, name_or_id)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    ports = list(conn.network.ports(device_id=router.id))
    gateway_port_id: str | None = None
    interface_port_ids: set[str] = set()
    port_fixed_ips: dict[str, list[dict]] = {}
    for port in ports:
        port_fixed_ips[port.id] = port.fixed_ips
        if port.device_owner == GATEWAY_DEVICE_OWNER:
            gateway_port_id = port.id
        elif port.device_owner == INTERFACE_DEVICE_OWNER:
            interface_port_ids.add(port.id)

    ovn_name = f"{NEUTRON_PREFIX}{router.id}"
    print(f"\nRouter {router.name} ({router.id})")
    print(f"OVN Logical_Router: {ovn_name}")

    lr_rows = ovn.nbctl_find(conn_ctx, "Logical_Router", f"name={ovn_name}")
    if not lr_rows:
        typer.echo(
            f"\nERROR: no OVN Logical_Router named {ovn_name} "
            "-- router may not be scheduled in OVN yet.",
            err=True,
        )
        raise typer.Exit(1)
    lr = lr_rows[0]
    chassis_option = lr.get("options", {}).get("chassis")
    router_is_centralized = bool(chassis_option)
    router_type = (
        f"centralized (options:chassis={chassis_option})"
        if router_is_centralized
        else "distributed"
    )
    print(f"Type: {router_type}")

    lrp_uuids = set(ovn.as_list(lr.get("ports")))
    all_lrps = ovn.nbctl_list(conn_ctx, "Logical_Router_Port")
    lrps = _rows_by_uuid(all_lrps, lrp_uuids)

    hcg_rows = {
        row["_uuid"]: row for row in ovn.nbctl_list(conn_ctx, "HA_Chassis_Group")
    }
    ha_chassis_rows = {
        row["_uuid"]: row for row in ovn.nbctl_list(conn_ctx, "HA_Chassis")
    }
    gateway_chassis_rows = {
        row["_uuid"]: row for row in ovn.nbctl_list(conn_ctx, "Gateway_Chassis")
    }
    sb_chassis_by_name = {
        row["name"]: row for row in ovn.sbctl_list(conn_ctx, "Chassis")
    }
    tables = ChassisTables(
        hcg_rows=hcg_rows,
        ha_chassis_rows=ha_chassis_rows,
        gateway_chassis_rows=gateway_chassis_rows,
        sb_chassis_by_name=sb_chassis_by_name,
    )
    router_chassis_live = "alive" if chassis_option in sb_chassis_by_name else "DEAD"
    router_chassis_physnets = _chassis_physical_networks(
        sb_chassis_by_name.get(chassis_option)
    )
    # Fetched once and reused for every port below -- this is a fleet-wide
    # table, so refetching it per port would scale with cluster size.
    all_lsp_rows = ovn.nbctl_list(conn_ctx, "Logical_Switch_Port")
    lsp_by_name = {row["name"]: row for row in all_lsp_rows}
    switch_row_cache: dict[str, dict | None] = {}

    print("\nRouter ports:")
    for lrp in lrps:
        port_id = lrp["name"].removeprefix("lrp-")
        role = _lrp_role(lrp["name"], gateway_port_id, interface_port_ids)
        networks = ", ".join(ovn.as_list(lrp.get("networks")))
        neutron_ips = ", ".join(
            fip["ip_address"] for fip in port_fixed_ips.get(port_id, [])
        )
        print(f"  - {lrp['name']} [{role}]")
        print(f"      Neutron port      : {port_id}")
        print(f"      OVN networks      : {networks or '(none)'}")
        print(f"      Neutron fixed IPs : {neutron_ips or '(none)'}")

        peer_lsp = _find_lsp(lsp_by_name, port_id)
        switch_name = (
            (peer_lsp or {}).get("external_ids", {}).get("neutron:network_name")
        )
        tags = _localnet_tags(conn_ctx, switch_name, all_lsp_rows, switch_row_cache)
        print(f"      Network VLAN tag  : {tags}")

        hcg_uuid = lrp.get("ha_chassis_group")
        gw_chassis_uuids = ovn.as_list(lrp.get("gateway_chassis"))
        if hcg_uuid:
            summary = _describe_hcg(hcg_uuid, tables)
            print(f"      HA_Chassis_Group  : {summary}")
        elif gw_chassis_uuids:
            # VLAN/FLAT distributed gateways are scheduled by OVN's own L3
            # scheduler via gateway_chassis, not ha_chassis_group.
            summary = _describe_chassis_refs(
                gw_chassis_uuids, tables.gateway_chassis_rows, tables.sb_chassis_by_name
            )
            print(f"      Gateway_Chassis   : {summary}")
        elif router_is_centralized:
            # options:chassis alone pins every port on a centralized router
            # (gateway included) -- ovn-northd ignores/warns on
            # ha_chassis_group here regardless of port role, so an unlinked
            # HCG is expected, not a bug.
            pin = (
                f"{chassis_option} ({router_chassis_live}, "
                f"physnets={router_chassis_physnets})"
            )
            print(f"      Pinned chassis    : {pin}")
        elif role == "internal":
            # Upstream OVN never sets ha_chassis_group on an internal
            # router-interface LRP by default (only understack's
            # vxlan-specific workaround does, and only for genuinely
            # distributed routers) -- unset here is the normal state.
            print(
                "      HA_Chassis_Group  : (none) -- not set by default "
                "on internal ports"
            )
        else:
            print(
                "      HA_Chassis_Group  : NOT LINKED (likely bug -- no "
                "ha_chassis_group or gateway_chassis found; see "
                "scripts/cleanup_dead_ovn_ha_chassis.py)"
            )

    print("\nNAT rules:")
    nat_uuids = set(ovn.as_list(lr.get("nat")))
    all_nat_rows = ovn.nbctl_list(conn_ctx, "NAT")
    nat_rows = _rows_by_uuid(all_nat_rows, nat_uuids)
    resolved_ports: dict[str, Any] = {}
    if not nat_rows:
        print("  (none)")
    for nat in nat_rows:
        nat_type = nat.get("type", "?")
        external_ip = nat.get("external_ip") or "-"
        logical_ip = nat.get("logical_ip") or "-"
        line = f"  {nat_type:<14} external={external_ip:<16} logical={logical_ip}"
        try:
            port_id, port = _resolve_nat_port(conn, nat)
        except Exception as exc:
            print(f"{line}  -> ERROR resolving port: {exc}")
            continue
        if port_id and port is None:
            line += f"  -> port {port_id} NOT FOUND (dangling NAT rule?)"
        elif port is not None:
            line += f"  -> port {port.id}"
            resolved_ports[port.id] = port
        print(line)

    print("\nPorts:")
    if not resolved_ports:
        print("  (none)")
    for port in resolved_ports.values():
        fixed_ips = ", ".join(fip["ip_address"] for fip in (port.fixed_ips or []))
        print(f"  {port.id} ({port.name or '(unnamed)'})")
        print(f"      Fixed IPs        : {fixed_ips or '(none)'}")
        print(f"      Owner            : {_describe_port_owner(conn, port)}")
        lsp_row = _find_lsp(lsp_by_name, port.id)
        print(f"      OVN LSP          : {_describe_lsp(lsp_row)}")
        lsp_hcg_uuid = (lsp_row or {}).get("ha_chassis_group")
        hcg_summary = _describe_hcg(lsp_hcg_uuid, tables)
        print(f"      HA_Chassis_Group : {hcg_summary}")

    if flows:
        print("\nSouthbound logical flows (ovn-sbctl lflow-list):")
        print(ovn.sbctl_lflow_list(conn_ctx, ovn_name).rstrip())


@app.command("list")
def list_routers(ctx: typer.Context) -> None:
    """List routers, cross-referencing presence in OpenStack (Neutron) and OVN."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx, include_openstack=True)

    try:
        conn = osclient.get_connection(conn_ctx.os_cloud)
    except Exception as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    openstack_routers = {r.id: r for r in conn.network.routers()}

    ovn_router_names: dict[str, str] = {}
    for row in ovn.nbctl_list(conn_ctx, "Logical_Router"):
        name = row.get("name") or ""
        if name.startswith(NEUTRON_PREFIX):
            ovn_router_names[name.removeprefix(NEUTRON_PREFIX)] = name

    all_ids = set(openstack_routers) | set(ovn_router_names)
    table_rows = []
    for router_id in all_ids:
        os_router = openstack_routers.get(router_id)
        # Flavored routers (e.g. VRF) are handled by a different L3 backend
        # entirely and never get an OVN Logical_Router -- "NO" there would
        # look like a bug when it's actually expected.
        flavored = bool(os_router and getattr(os_router, "flavor_id", None))
        name = os_router.name if os_router else "(unknown)"
        in_openstack = "yes" if os_router else "NO"
        in_ovn = (
            "n/a (flavored)"
            if flavored
            else ("yes" if router_id in ovn_router_names else "NO")
        )
        table_rows.append((name, router_id, in_openstack, in_ovn))
    table_rows.sort(key=lambda row: row[0].lower())

    print()
    if not table_rows:
        print("(no routers found)")
        return

    name_width = max(len("NAME"), *(len(row[0]) for row in table_rows))
    id_width = max(len("ID"), *(len(row[1]) for row in table_rows))
    header = f"{'NAME':<{name_width}}  {'ID':<{id_width}}  {'OPENSTACK':<9}  OVN"
    print(header)
    print("-" * len(header))
    for name, router_id, in_openstack, in_ovn in table_rows:
        name_col = f"{name:<{name_width}}"
        id_col = f"{router_id:<{id_width}}"
        os_col = f"{in_openstack:<9}"
        print(f"{name_col}  {id_col}  {os_col}  {in_ovn}")
