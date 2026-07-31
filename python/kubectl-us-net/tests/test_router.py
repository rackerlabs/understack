import types

import typer
from openstack import exceptions as os_exc
from typer.testing import CliRunner

from us_net.commands import router
from us_net.connection import ConnectionContext

runner = CliRunner()


def make_app():
    app = typer.Typer()

    @app.callback()
    def main(ctx: typer.Context) -> None:
        ctx.obj = ConnectionContext(
            kube_context=None,
            namespace="openstack",
            nb_pod="ovn-ovsdb-nb-0",
            sb_pod="ovn-ovsdb-sb-0",
            os_cloud="dev-cloud",
        )

    app.add_typer(router.app, name="router")
    return app


class FakeRouter:
    id = "rtr-1"
    name = "test-router"


class PortNotFound(os_exc.ResourceNotFound):
    pass


class ServerNotFound(Exception):
    pass


class FakeNetworkAPI:
    def __init__(self, router_ports, all_ports=None, routers_list=None):
        self._router_ports = router_ports
        self._all_ports = {p.id: p for p in (all_ports or router_ports)}
        self._routers_list = routers_list or []

    def ports(self, device_id=None, fixed_ips=None):
        if fixed_ips is not None:
            ip = fixed_ips.split("=", 1)[1]
            return [
                p
                for p in self._all_ports.values()
                if any(fip["ip_address"] == ip for fip in p.fixed_ips)
            ]
        return self._router_ports

    def get_port(self, port_id):
        if port_id not in self._all_ports:
            raise PortNotFound(f"port {port_id} not found")
        return self._all_ports[port_id]

    def routers(self):
        return self._routers_list


class FakeComputeAPI:
    def __init__(self, servers=None):
        self._servers = servers or {}

    def get_server(self, server_id):
        if server_id not in self._servers:
            raise ServerNotFound(f"server {server_id} not found")
        return self._servers[server_id]


class FakeConfig:
    config = {}


class FakeConnection:
    def __init__(self, ports, all_ports=None, servers=None, routers_list=None):
        self.network = FakeNetworkAPI(ports, all_ports, routers_list)
        self.compute = FakeComputeAPI(servers)
        self.config = FakeConfig()


def make_ports():
    return [
        types.SimpleNamespace(
            id="gw-1",
            name=None,
            device_owner="network:router_gateway",
            device_id=None,
            fixed_ips=[{"ip_address": "203.0.113.5"}],
        ),
        types.SimpleNamespace(
            id="int-1",
            name=None,
            device_owner="network:router_interface",
            device_id=None,
            fixed_ips=[{"ip_address": "192.168.0.1"}],
        ),
    ]


def make_bound_port():
    """A tenant instance port that a floating-IP NAT rule points to."""
    return types.SimpleNamespace(
        id="vm-port-1",
        name="vm-port",
        device_owner="compute:nova",
        device_id="server-1",
        fixed_ips=[{"ip_address": "192.168.0.32"}],
    )


def patch_common(monkeypatch, *, hcg_linked=True, chassis_alive=True, centralized=True):
    monkeypatch.setattr(
        router.osclient,
        "get_connection",
        lambda os_cloud: FakeConnection(
            make_ports(),
            all_ports=[*make_ports(), make_bound_port()],
            servers={"server-1": types.SimpleNamespace(name="my-server")},
        ),
    )
    monkeypatch.setattr(
        router.osclient, "resolve_router", lambda conn, name_or_id: FakeRouter()
    )

    lr_row = {
        "_uuid": "lr-uuid",
        "name": "neutron-rtr-1",
        "options": {"chassis": "chassis-a"} if centralized else {},
        "ports": ["lrp-uuid-gw", "lrp-uuid-int"],
        "nat": ["nat-uuid-1", "nat-uuid-2"],
    }
    lrp_rows = [
        {
            "_uuid": "lrp-uuid-gw",
            "name": "lrp-gw-1",
            "networks": ["203.0.113.5/24"],
            "ha_chassis_group": [],
        },
        {
            "_uuid": "lrp-uuid-int",
            "name": "lrp-int-1",
            "networks": ["192.168.0.1/24"],
            "ha_chassis_group": "hcg-uuid-1" if hcg_linked else [],
        },
        {
            "_uuid": "lrp-uuid-unrelated",
            "name": "lrp-other",
            "networks": ["10.0.0.1/24"],
            "ha_chassis_group": [],
        },
    ]
    hcg_rows = [
        {"_uuid": "hcg-uuid-1", "name": "neutron-net-1", "ha_chassis": ["hac-uuid-1"]}
    ]
    ha_chassis_rows = [
        {"_uuid": "hac-uuid-1", "chassis_name": "chassis-a", "priority": 32767}
    ]
    chassis_rows = (
        [
            {
                "name": "chassis-a",
                "other_config": {"ovn-bridge-mappings": "f20-1-network:br-ex"},
            }
        ]
        if chassis_alive
        else []
    )
    nat_rows = [
        {
            "_uuid": "nat-uuid-1",
            "type": "dnat_and_snat",
            "external_ip": "204.232.163.17",
            "logical_ip": "192.168.0.32",
            "logical_port": "vm-port-1",
            "external_ids": {"neutron:fip_port_id": "vm-port-1"},
        },
        {
            "_uuid": "nat-uuid-2",
            "type": "snat",
            "external_ip": "204.232.163.55",
            "logical_ip": "192.168.0.0/24",
            "logical_port": "",
            "external_ids": {},
        },
    ]

    localnet_lsp_ext = {
        "_uuid": "lsp-uuid-localnet-ext",
        "name": "uplink-ext-1",
        "type": "localnet",
        "tag": 1804,
    }
    localnet_lsp_int = {
        "_uuid": "lsp-uuid-localnet-int",
        "name": "uplink-int-1",
        "type": "localnet",
        "tag": 1802,
    }
    peer_lsp_gw = {
        "_uuid": "lsp-uuid-gw",
        "name": "gw-1",
        "type": "router",
        "addresses": "router",
        "up": True,
        "external_ids": {"neutron:network_name": "neutron-net-ext"},
        "ha_chassis_group": [],
    }
    peer_lsp_int = {
        "_uuid": "lsp-uuid-int",
        "name": "int-1",
        "type": "router",
        "addresses": "router",
        "up": True,
        "external_ids": {"neutron:network_name": "neutron-net-int"},
        "ha_chassis_group": [],
    }
    peer_lsp_vm = {
        "_uuid": "lsp-uuid-vm",
        "name": "vm-port-1",
        "type": "",
        "addresses": "fa:16:3e:00:00:01 192.168.0.32",
        "up": True,
        "ha_chassis_group": [],
    }
    all_lsp_rows = [
        localnet_lsp_ext,
        localnet_lsp_int,
        peer_lsp_gw,
        peer_lsp_int,
        peer_lsp_vm,
    ]
    lsp_rows_by_name = {row["name"]: row for row in all_lsp_rows}
    switch_rows_by_name = {
        "neutron-net-ext": {
            "_uuid": "switch-ext",
            "name": "neutron-net-ext",
            "ports": ["lsp-uuid-localnet-ext", "lsp-uuid-gw"],
        },
        "neutron-net-int": {
            "_uuid": "switch-int",
            "name": "neutron-net-int",
            "ports": ["lsp-uuid-localnet-int", "lsp-uuid-int"],
        },
    }

    def fake_nbctl_find(ctx, table, condition):
        if table == "Logical_Router":
            assert condition == "name=neutron-rtr-1"
            return [lr_row]
        if table == "Logical_Switch_Port":
            port_id = condition.removeprefix("name=")
            row = lsp_rows_by_name.get(port_id)
            return [row] if row else []
        if table == "Logical_Switch":
            name = condition.removeprefix("name=")
            row = switch_rows_by_name.get(name)
            return [row] if row else []
        raise AssertionError(f"unexpected nbctl_find table {table!r}")

    def fake_nbctl_list(ctx, table):
        return {
            "Logical_Router_Port": lrp_rows,
            "HA_Chassis_Group": hcg_rows,
            "HA_Chassis": ha_chassis_rows,
            "Gateway_Chassis": [],
            "NAT": nat_rows,
            "Logical_Switch_Port": all_lsp_rows,
        }[table]

    def fake_sbctl_list(ctx, table):
        assert table == "Chassis"
        return chassis_rows

    monkeypatch.setattr(router.ovn, "nbctl_find", fake_nbctl_find)
    monkeypatch.setattr(router.ovn, "nbctl_list", fake_nbctl_list)
    monkeypatch.setattr(router.ovn, "sbctl_list", fake_sbctl_list)
    monkeypatch.setattr(
        router.ovn, "sbctl_lflow_list", lambda ctx, name: "FLOW_TABLE_OUTPUT\n"
    )


def test_localnet_tags_returns_unknown_network_for_missing_switch_name():
    assert router._localnet_tags(None, None, [], {}) == "(unknown network)"


def test_localnet_tags_returns_switch_not_found(monkeypatch):
    monkeypatch.setattr(router.ovn, "nbctl_find", lambda ctx, table, condition: [])
    assert router._localnet_tags(None, "neutron-missing", [], {}) == (
        "(switch not found)"
    )


def test_localnet_tags_returns_no_localnet_port(monkeypatch):
    monkeypatch.setattr(
        router.ovn,
        "nbctl_find",
        lambda ctx, table, condition: [{"_uuid": "sw-1", "ports": ["lsp-1"]}],
    )
    all_lsp_rows = [{"_uuid": "lsp-1", "type": "", "tag": []}]
    assert router._localnet_tags(None, "neutron-net-1", all_lsp_rows, {}) == (
        "(no localnet port)"
    )


def test_localnet_tags_joins_multiple_tags(monkeypatch):
    monkeypatch.setattr(
        router.ovn,
        "nbctl_find",
        lambda ctx, table, condition: [{"_uuid": "sw-1", "ports": ["lsp-1", "lsp-2"]}],
    )
    all_lsp_rows = [
        {"_uuid": "lsp-1", "type": "localnet", "tag": 1800},
        {"_uuid": "lsp-2", "type": "localnet", "tag": 1801},
        {"_uuid": "lsp-3", "type": "router", "tag": []},
    ]
    assert router._localnet_tags(None, "neutron-net-1", all_lsp_rows, {}) == (
        "1800, 1801"
    )


def test_localnet_tags_caches_switch_lookup_across_calls(monkeypatch):
    calls = []

    def fake_nbctl_find(ctx, table, condition):
        calls.append(condition)
        return [{"_uuid": "sw-1", "ports": []}]

    monkeypatch.setattr(router.ovn, "nbctl_find", fake_nbctl_find)
    cache: dict = {}
    router._localnet_tags(None, "neutron-net-1", [], cache)
    router._localnet_tags(None, "neutron-net-1", [], cache)
    assert calls == ["name=neutron-net-1"]  # only looked up once, then cached


def test_router_show_reports_gateway_and_internal_ports(monkeypatch):
    patch_common(monkeypatch)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "lrp-gw-1 [gateway]" in result.output
    assert "203.0.113.5/24" in result.output
    assert "203.0.113.5" in result.output  # Neutron fixed IP
    assert "lrp-int-1 [internal]" in result.output
    assert "lrp-other" not in result.output  # unrelated LRP filtered out
    assert "Network VLAN tag  : 1804" in result.output  # gateway's uplink tag
    assert "Network VLAN tag  : 1802" in result.output  # internal's uplink tag
    # gateway HCG is unlinked but the router is centralized, so that's expected
    assert (
        "Pinned chassis    : chassis-a (alive, physnets=f20-1-network)" in result.output
    )
    assert (
        "neutron-net-1 -> chassis-a (priority=32767, alive, physnets=f20-1-network)"
        in result.output
    )
    assert "dnat_and_snat" in result.output
    assert "external=204.232.163.17" in result.output
    assert "logical=192.168.0.32" in result.output
    assert "-> port vm-port-1" in result.output
    assert "snat" in result.output
    assert "logical=192.168.0.0/24" in result.output
    assert "FLOW_TABLE_OUTPUT" not in result.output  # --flows not passed


def test_router_show_ports_section_lists_resolved_nat_ports(monkeypatch):
    patch_common(monkeypatch)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "\nPorts:\n" in result.output
    assert "vm-port-1 (vm-port)" in result.output
    assert "Fixed IPs        : 192.168.0.32" in result.output
    assert "Owner            : server server-1 (my-server)" in result.output
    assert (
        "OVN LSP          : type=(normal), up, addresses=fa:16:3e:00:00:01 192.168.0.32"
        in result.output
    )
    # vm-port-1's LSP has no ha_chassis_group of its own in the base fixture
    assert "HA_Chassis_Group : NOT LINKED" in result.output


def test_router_show_ports_section_shows_lsp_level_hcg(monkeypatch):
    patch_common(monkeypatch)
    monkeypatch.setattr(
        router,
        "_find_lsp",
        lambda conn_ctx, port_id: (
            {
                "type": "",
                "addresses": "fa:16:3e:00:00:01 192.168.0.32",
                "up": True,
                "ha_chassis_group": "hcg-uuid-1",
            }
            if port_id == "vm-port-1"
            else None
        ),
    )
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    ports_section = result.output.split("\nPorts:\n", 1)[1]
    assert (
        "HA_Chassis_Group : neutron-net-1 -> "
        "chassis-a (priority=32767, alive, physnets=f20-1-network)" in ports_section
    )


def test_router_show_router_ports_show_neutron_port_id_not_in_ports_section(
    monkeypatch,
):
    patch_common(monkeypatch)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    router_ports_section = result.output.split("\nRouter ports:\n", 1)[1].split(
        "\nNAT rules:\n", 1
    )[0]
    assert "Neutron port      : gw-1" in router_ports_section
    assert "Neutron port      : int-1" in router_ports_section
    # the router's own ports restate nothing new in Ports: -- only NAT-target
    # ports (e.g. floating-IP-bound VMs) belong there
    ports_section = result.output.split("\nPorts:\n", 1)[1]
    assert "gw-1 ((unnamed))" not in ports_section
    assert "int-1 ((unnamed))" not in ports_section


def test_describe_lsp_flags_dangling_reference():
    assert router._describe_lsp(None) == "NOT FOUND (dangling?)"


def make_chassis_tables(**overrides) -> router.ChassisTables:
    defaults = dict(
        hcg_rows={}, ha_chassis_rows={}, gateway_chassis_rows={}, sb_chassis_by_name={}
    )
    defaults.update(overrides)
    return router.ChassisTables(**defaults)


def test_describe_hcg_not_linked_when_uuid_missing():
    assert router._describe_hcg(None, make_chassis_tables()) == "NOT LINKED"


def test_describe_hcg_flags_dangling_hcg_row():
    result = router._describe_hcg("missing-hcg", make_chassis_tables())
    assert result == "missing-hcg (row not found!)"


def test_describe_hcg_resolves_via_bundled_tables():
    tables = make_chassis_tables(
        hcg_rows={"hcg-1": {"name": "neutron-net-1", "ha_chassis": ["hac-1"]}},
        ha_chassis_rows={"hac-1": {"chassis_name": "chassis-a", "priority": 32767}},
        sb_chassis_by_name={"chassis-a": {"name": "chassis-a"}},
    )
    result = router._describe_hcg("hcg-1", tables)
    expected = (
        "neutron-net-1 -> chassis-a (priority=32767, alive, "
        "physnets=(no ovn-bridge-mappings configured))"
    )
    assert result == expected


def test_describe_lsp_summarizes_found_row():
    row = {"type": "router", "addresses": "router", "up": True}
    assert router._describe_lsp(row) == "type=router, up, addresses=router"


def test_describe_lsp_defaults_missing_type_and_down_state():
    row = {"addresses": ["fa:16:3e:00:00:01", "192.168.0.32"], "up": False}
    assert (
        router._describe_lsp(row)
        == "type=(normal), down, addresses=fa:16:3e:00:00:01, 192.168.0.32"
    )


def test_router_show_ports_section_flags_dangling_lsp(monkeypatch):
    patch_common(monkeypatch)
    monkeypatch.setattr(router, "_find_lsp", lambda conn_ctx, port_id: None)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    ports_section = result.output.split("\nPorts:\n", 1)[1]
    assert ports_section.count("OVN LSP          : NOT FOUND (dangling?)") == 1
    # with no LSP row at all, there's no ha_chassis_group to resolve either
    assert ports_section.count("HA_Chassis_Group : NOT LINKED") == 1


def test_router_show_ports_section_is_empty_with_no_nat_rules(monkeypatch):
    patch_common(monkeypatch)
    monkeypatch.setattr(
        router.ovn,
        "nbctl_list",
        lambda ctx, table: {
            "Logical_Router_Port": [
                {
                    "_uuid": "lrp-uuid-gw",
                    "name": "lrp-gw-1",
                    "networks": ["203.0.113.5/24"],
                    "ha_chassis_group": [],
                },
                {
                    "_uuid": "lrp-uuid-int",
                    "name": "lrp-int-1",
                    "networks": ["192.168.0.1/24"],
                    "ha_chassis_group": "hcg-uuid-1",
                },
            ],
            "HA_Chassis_Group": [
                {
                    "_uuid": "hcg-uuid-1",
                    "name": "neutron-net-1",
                    "ha_chassis": ["hac-uuid-1"],
                }
            ],
            "HA_Chassis": [
                {"_uuid": "hac-uuid-1", "chassis_name": "chassis-a", "priority": 32767}
            ],
            "Gateway_Chassis": [],
            "NAT": [],
            "Logical_Switch_Port": [],
        }[table],
    )
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    # the router's own ports still appear in Router ports:, by Neutron port id
    router_ports_section = result.output.split("\nRouter ports:\n", 1)[1].split(
        "\nNAT rules:\n", 1
    )[0]
    assert "Neutron port      : gw-1" in router_ports_section
    assert "Neutron port      : int-1" in router_ports_section
    assert "\nPorts:\n  (none)" in result.output


def test_router_show_nat_snat_rule_has_no_port_link(monkeypatch):
    patch_common(monkeypatch)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    snat_line = next(
        line for line in result.output.splitlines() if line.strip().startswith("snat")
    )
    assert "-> port" not in snat_line


def test_router_show_nat_dangling_port_reference_is_flagged(monkeypatch):
    patch_common(monkeypatch)
    monkeypatch.setattr(
        router.ovn,
        "nbctl_list",
        lambda ctx, table: {
            "Logical_Router_Port": [],
            "HA_Chassis_Group": [],
            "HA_Chassis": [],
            "Gateway_Chassis": [],
            "NAT": [
                {
                    "_uuid": "nat-uuid-1",
                    "type": "dnat_and_snat",
                    "external_ip": "204.232.163.99",
                    "logical_ip": "192.168.0.99",
                    "logical_port": "deleted-port-id",
                    "external_ids": {"neutron:fip_port_id": "deleted-port-id"},
                }
            ],
            "Logical_Switch_Port": [],
        }[table],
    )
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "port deleted-port-id NOT FOUND (dangling NAT rule?)" in result.output


def test_router_show_nat_transient_error_is_not_reported_as_dangling(monkeypatch):
    patch_common(monkeypatch)

    def boom(*args, **kwargs):
        raise TimeoutError("connection timed out")

    monkeypatch.setattr(
        router.osclient,
        "get_connection",
        lambda os_cloud: FakeConnection(
            make_ports(), all_ports=[*make_ports(), make_bound_port()], servers={}
        ),
    )
    monkeypatch.setattr(router, "_resolve_nat_port", lambda conn, nat: boom())
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "ERROR resolving port: connection timed out" in result.output
    assert "dangling NAT rule" not in result.output


def test_describe_chassis_refs_sorts_by_priority_descending():
    chassis_rows = {
        "hac-low": {"chassis_name": "chassis-backup", "priority": 100},
        "hac-high": {"chassis_name": "chassis-primary", "priority": 32767},
    }
    sb_chassis_by_name = {
        "chassis-backup": {"name": "chassis-backup"},
        "chassis-primary": {"name": "chassis-primary"},
    }
    summary = router._describe_chassis_refs(
        ["hac-low", "hac-high"], chassis_rows, sb_chassis_by_name
    )
    primary_pos = summary.index("chassis-primary")
    backup_pos = summary.index("chassis-backup")
    assert primary_pos < backup_pos  # higher priority (32767) printed first


def test_router_show_flags_dead_chassis(monkeypatch):
    patch_common(monkeypatch, chassis_alive=False)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "DEAD" in result.output


def test_router_show_flows_flag_dumps_sb_flows(monkeypatch):
    patch_common(monkeypatch)
    result = runner.invoke(make_app(), ["router", "show", "test-router", "--flows"])
    assert result.exit_code == 0
    assert "FLOW_TABLE_OUTPUT" in result.output


def test_router_show_missing_router_errors_cleanly(monkeypatch):
    monkeypatch.setattr(
        router.osclient, "get_connection", lambda os_cloud: FakeConnection([])
    )

    def raise_lookup(conn, name_or_id):
        raise LookupError(f"router {name_or_id!r} not found")

    monkeypatch.setattr(router.osclient, "resolve_router", raise_lookup)
    result = runner.invoke(make_app(), ["router", "show", "missing"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_router_show_missing_ovn_logical_router_errors(monkeypatch):
    monkeypatch.setattr(
        router.osclient, "get_connection", lambda os_cloud: FakeConnection(make_ports())
    )
    monkeypatch.setattr(
        router.osclient, "resolve_router", lambda conn, name_or_id: FakeRouter()
    )
    monkeypatch.setattr(router.ovn, "nbctl_find", lambda ctx, table, condition: [])
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 1


def test_lrp_role_returns_unknown_for_unrecognized_port():
    role = router._lrp_role("lrp-stray", "gw-1", {"int-1"})
    assert role == "unknown"


def test_rows_by_uuid_filters_to_matching_rows_only():
    rows = [
        {"_uuid": "a", "name": "keep-a"},
        {"_uuid": "b", "name": "drop-b"},
        {"_uuid": "c", "name": "keep-c"},
    ]
    result = router._rows_by_uuid(rows, {"a", "c"})
    assert result == [
        {"_uuid": "a", "name": "keep-a"},
        {"_uuid": "c", "name": "keep-c"},
    ]


def test_rows_by_uuid_ignores_rows_missing_uuid_key():
    rows = [{"name": "no-uuid-field"}, {"_uuid": "a", "name": "keep-a"}]
    assert router._rows_by_uuid(rows, {"a"}) == [{"_uuid": "a", "name": "keep-a"}]


def test_rows_by_uuid_returns_empty_for_no_matches():
    rows = [{"_uuid": "a"}, {"_uuid": "b"}]
    assert router._rows_by_uuid(rows, {"z"}) == []


def test_router_show_flags_dangling_hcg_reference(monkeypatch):
    patch_common(monkeypatch)
    # Point the internal LRP's ha_chassis_group at a uuid with no matching
    # HA_Chassis_Group row -- a dangling reference, the exact referential
    # integrity gap cleanup_dead_ovn_ha_chassis.py exists to repair.
    monkeypatch.setattr(
        router.ovn,
        "nbctl_list",
        lambda ctx, table: {
            "Logical_Router_Port": [
                {
                    "_uuid": "lrp-uuid-gw",
                    "name": "lrp-gw-1",
                    "networks": ["203.0.113.5/24"],
                    "ha_chassis_group": [],
                },
                {
                    "_uuid": "lrp-uuid-int",
                    "name": "lrp-int-1",
                    "networks": ["192.168.0.1/24"],
                    "ha_chassis_group": "missing-hcg-uuid",
                },
            ],
            "HA_Chassis_Group": [],
            "HA_Chassis": [],
            "Gateway_Chassis": [],
            "NAT": [],
            "Logical_Switch_Port": [],
        }[table],
    )
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "missing-hcg-uuid (row not found!)" in result.output


def test_router_show_skips_dangling_ha_chassis_reference(monkeypatch):
    patch_common(monkeypatch)
    # The HCG references a HA_Chassis uuid that no longer has a row --
    # should be silently skipped rather than crashing.
    monkeypatch.setattr(
        router.ovn,
        "nbctl_list",
        lambda ctx, table: {
            "Logical_Router_Port": [
                {
                    "_uuid": "lrp-uuid-int",
                    "name": "lrp-int-1",
                    "networks": ["192.168.0.1/24"],
                    "ha_chassis_group": "hcg-uuid-1",
                },
            ],
            "HA_Chassis_Group": [
                {
                    "_uuid": "hcg-uuid-1",
                    "name": "neutron-net-1",
                    "ha_chassis": ["missing-hac"],
                }
            ],
            "HA_Chassis": [],
            "Gateway_Chassis": [],
            "NAT": [],
            "Logical_Switch_Port": [],
        }[table],
    )
    monkeypatch.setattr(
        router.ovn,
        "nbctl_find",
        lambda ctx, table, condition: [
            {
                "_uuid": "lr-uuid",
                "name": "neutron-rtr-1",
                "options": {"chassis": "chassis-a"},
                "ports": ["lrp-uuid-int"],
            }
        ],
    )
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "neutron-net-1 -> (empty)" in result.output


def test_router_show_unlinked_hcg_is_expected_on_centralized_router_both_ports(
    monkeypatch,
):
    patch_common(monkeypatch, hcg_linked=False, centralized=True)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    router_ports_section = result.output.split("\nRouter ports:\n", 1)[1].split(
        "\nNAT rules:\n", 1
    )[0]
    assert "lrp-gw-1 [gateway]" in router_ports_section
    assert "lrp-int-1 [internal]" in router_ports_section
    # options:chassis pins every port on a centralized router -- gateway
    # included -- so an unlinked HCG on either port is expected, not a bug
    assert router_ports_section.count("Pinned chassis    : chassis-a (alive") == 2
    assert "NOT LINKED" not in router_ports_section


def test_router_show_on_distributed_router_only_flags_the_gateway_port(
    monkeypatch,
):
    patch_common(monkeypatch, hcg_linked=False, centralized=False)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "Type: distributed" in result.output
    assert "Pinned chassis" not in result.output
    # the gateway port has neither ha_chassis_group nor gateway_chassis --
    # that's a real bug (no scheduling info at all)
    assert result.output.count("NOT LINKED (likely bug") == 1
    # upstream OVN never sets ha_chassis_group on internal LRPs by default,
    # so its absence there is expected, not a bug
    assert "HA_Chassis_Group  : (none) -- not set by default on internal ports" in (
        result.output
    )


def test_router_show_vlan_flat_distributed_gateway_uses_gateway_chassis(
    monkeypatch,
):
    # VLAN/FLAT distributed gateways are scheduled by OVN's own L3 scheduler
    # via gateway_chassis, not ha_chassis_group -- a healthy such router
    # should not be flagged as "likely bug".
    patch_common(monkeypatch, hcg_linked=False, centralized=False)
    monkeypatch.setattr(
        router.ovn,
        "nbctl_list",
        lambda ctx, table: {
            "Logical_Router_Port": [
                {
                    "_uuid": "lrp-uuid-gw",
                    "name": "lrp-gw-1",
                    "networks": ["203.0.113.5/24"],
                    "ha_chassis_group": [],
                    "gateway_chassis": "gwc-uuid-1",
                },
                {
                    "_uuid": "lrp-uuid-int",
                    "name": "lrp-int-1",
                    "networks": ["192.168.0.1/24"],
                    "ha_chassis_group": [],
                },
            ],
            "HA_Chassis_Group": [],
            "HA_Chassis": [],
            "Gateway_Chassis": [
                {
                    "_uuid": "gwc-uuid-1",
                    "chassis_name": "chassis-a",
                    "priority": 32767,
                }
            ],
            "NAT": [],
            "Logical_Switch_Port": [],
        }[table],
    )
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert "Type: distributed" in result.output
    assert "NOT LINKED (likely bug" not in result.output
    assert (
        "Gateway_Chassis   : chassis-a (priority=32767, alive, "
        "physnets=f20-1-network)" in result.output
    )


def test_router_show_pinned_chassis_flags_dead_chassis(monkeypatch):
    patch_common(monkeypatch, hcg_linked=False, centralized=True, chassis_alive=False)
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert (
        "Pinned chassis    : chassis-a (DEAD, physnets=(chassis not in SB))"
        in result.output
    )


def test_router_show_pinned_chassis_flags_missing_bridge_mappings(monkeypatch):
    patch_common(monkeypatch, hcg_linked=False, centralized=True)
    monkeypatch.setattr(
        router.ovn, "sbctl_list", lambda ctx, table: [{"name": "chassis-a"}]
    )
    result = runner.invoke(make_app(), ["router", "show", "test-router"])
    assert result.exit_code == 0
    assert (
        "Pinned chassis    : chassis-a (alive, "
        "physnets=(no ovn-bridge-mappings configured))" in result.output
    )


class FakeOsRouter:
    def __init__(self, id, name, flavor_id=None):
        self.id = id
        self.name = name
        self.flavor_id = flavor_id


def patch_list_common(monkeypatch, openstack_routers, ovn_lr_names):
    monkeypatch.setattr(
        router.osclient,
        "get_connection",
        lambda os_cloud: FakeConnection([], routers_list=openstack_routers),
    )
    monkeypatch.setattr(
        router.ovn,
        "nbctl_list",
        lambda ctx, table: [{"name": name} for name in ovn_lr_names],
    )


def test_router_list_shows_a_row_per_router_matched_on_both_sides(monkeypatch):
    patch_list_common(
        monkeypatch,
        [FakeOsRouter("rtr-1", "router-one"), FakeOsRouter("rtr-2", "router-two")],
        ["neutron-rtr-1", "neutron-rtr-2"],
    )
    result = runner.invoke(make_app(), ["router", "list"])
    assert result.exit_code == 0
    assert "NAME" in result.output
    assert "ID" in result.output
    assert "OPENSTACK" in result.output
    assert "OVN" in result.output
    lines = result.output.splitlines()
    row_one = next(line for line in lines if line.startswith("router-one"))
    row_two = next(line for line in lines if line.startswith("router-two"))
    assert "rtr-1" in row_one and "yes" in row_one
    assert "rtr-2" in row_two and "yes" in row_two
    # rows are sorted by name
    assert lines.index(row_one) < lines.index(row_two)


def test_router_list_flags_router_missing_in_ovn(monkeypatch):
    patch_list_common(
        monkeypatch,
        [FakeOsRouter("rtr-1", "router-one"), FakeOsRouter("rtr-2", "router-two")],
        ["neutron-rtr-1"],
    )
    result = runner.invoke(make_app(), ["router", "list"])
    assert result.exit_code == 0
    row_two = next(
        line for line in result.output.splitlines() if line.startswith("router-two")
    )
    assert "NO" in row_two


def test_router_list_flags_router_missing_in_openstack(monkeypatch):
    patch_list_common(
        monkeypatch,
        [FakeOsRouter("rtr-1", "router-one")],
        ["neutron-rtr-1", "neutron-rtr-orphan"],
    )
    result = runner.invoke(make_app(), ["router", "list"])
    assert result.exit_code == 0
    row_orphan = next(
        line for line in result.output.splitlines() if line.startswith("(unknown)")
    )
    assert "rtr-orphan" in row_orphan
    assert "NO" in row_orphan  # not in OpenStack
    assert row_orphan.rstrip().endswith("yes")  # is in OVN


def test_router_list_ignores_non_neutron_ovn_routers(monkeypatch):
    patch_list_common(
        monkeypatch,
        [FakeOsRouter("rtr-1", "router-one")],
        ["neutron-rtr-1", "some-other-router"],
    )
    result = runner.invoke(make_app(), ["router", "list"])
    assert result.exit_code == 0
    assert "some-other-router" not in result.output
    # only one data row (plus header + separator)
    assert len(result.output.strip().splitlines()[-3:]) == 3


def test_router_list_marks_flavored_routers_as_not_applicable_for_ovn(monkeypatch):
    # Flavored (e.g. VRF) routers are handled by a different L3 backend and
    # never get an OVN Logical_Router -- "NO" there would look like a bug
    # when it's actually expected.
    patch_list_common(
        monkeypatch,
        [FakeOsRouter("rtr-vrf", "vrf-router", flavor_id="flavor-uuid")],
        [],
    )
    result = runner.invoke(make_app(), ["router", "list"])
    assert result.exit_code == 0
    row = next(
        line for line in result.output.splitlines() if line.startswith("vrf-router")
    )
    assert "yes" in row  # present in OpenStack
    assert "n/a (flavored)" in row


def test_router_list_reports_no_routers_found(monkeypatch):
    patch_list_common(monkeypatch, [], [])
    result = runner.invoke(make_app(), ["router", "list"])
    assert result.exit_code == 0
    assert "(no routers found)" in result.output


def test_router_list_reports_connection_error_cleanly(monkeypatch):
    def boom(os_cloud):
        raise RuntimeError("no cloud configured")

    monkeypatch.setattr(router.osclient, "get_connection", boom)
    result = runner.invoke(make_app(), ["router", "list"])
    assert result.exit_code == 1
    assert "ERROR: no cloud configured" in result.output
