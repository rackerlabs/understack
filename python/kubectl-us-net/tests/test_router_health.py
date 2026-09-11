import types

import pytest
import typer
from typer.testing import CliRunner

from us_net.commands import router
from us_net.commands import router_health
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


class FakeNetwork:
    def __init__(self, test_router, ports):
        self.router = test_router
        self._ports = ports

    def find_router(self, name_or_id):
        return self.router if name_or_id in {self.router.id, self.router.name} else None

    def ports(self, device_id=None, name=None, network_id=None):
        ports = self._ports
        if name is not None:
            ports = [port for port in ports if getattr(port, "name", None) == name]
        if device_id is not None:
            ports = [
                port for port in ports if getattr(port, "device_id", None) == device_id
            ]
        if network_id is not None:
            ports = [
                port
                for port in ports
                if getattr(port, "network_id", None) == network_id
            ]
        return ports


class FakeConnection:
    def __init__(self, network):
        self.network = network
        self.config = types.SimpleNamespace(config={})


def native_state(*, healthy=False, requested_chassis=""):
    test_router = types.SimpleNamespace(
        id="router-1", name="native-router", flavor_id=None
    )
    port = types.SimpleNamespace(
        id="gw-1",
        name="",
        network_id="net-1",
        device_id="router-1",
        device_owner="network:router_gateway",
        binding_host_id=requested_chassis,
    )
    uplink_port = types.SimpleNamespace(
        id="uplink-port-1",
        name="uplink-segment-1",
        network_id="net-1",
        device_id="",
        device_owner="",
    )
    options = (
        {
            "router-port": "lrp-gw-1",
            "nat-addresses": "router",
            "exclude-lb-vips-from-garp": "true",
            **({"requested-chassis": requested_chassis} if requested_chassis else {}),
        }
        if healthy
        else ({"requested-chassis": requested_chassis} if requested_chassis else {})
    )
    tables = {
        "Logical_Router": [
            {
                "_uuid": "lr-uuid",
                "name": "neutron-router-1",
                "ports": ["lrp-uuid"],
            }
        ],
        "Logical_Router_Port": [{"_uuid": "lrp-uuid", "name": "lrp-gw-1"}],
        "Logical_Switch_Port": [
            {
                "_uuid": "lsp-uuid",
                "name": "gw-1",
                "type": "router" if healthy else "",
                "addresses": ["router"] if healthy else [],
                "options": options,
            },
            {
                "_uuid": "uplink-lsp-uuid",
                "name": "uplink-segment-1",
                "type": "localnet",
                "addresses": ["unknown"],
                "tag": 1800,
                "options": {},
            },
        ],
        "Logical_Switch": [
            {
                "_uuid": "ls-uuid",
                "name": "neutron-net-1",
                "ports": ["lsp-uuid", "uplink-lsp-uuid"],
            }
        ],
        "HA_Chassis_Group": [],
        "HA_Chassis": [],
        "SB_Chassis": [],
    }
    return FakeConnection(FakeNetwork(test_router, [port, uplink_port])), tables


def patch_environment(
    monkeypatch,
    conn,
    tables,
    *,
    list_calls=None,
    find_calls=None,
    record_calls=None,
    sb_list_calls=None,
):
    monkeypatch.setattr(router_health.osclient, "get_connection", lambda cloud: conn)

    def list_rows(ctx, table):
        if list_calls is not None:
            list_calls.append(table)
        return tables[table]

    def find_rows(ctx, table, condition):
        if find_calls is not None:
            find_calls.append((table, condition))
        column, value = condition.split("=", 1)
        if ":" in column:
            map_column, key = column.split(":", 1)
            key = key.replace(r"\:", ":")
            return [
                row
                for row in tables[table]
                if (row.get(map_column) or {}).get(key) == value
            ]
        return [row for row in tables[table] if row.get(column) == value]

    def list_records(ctx, table, records):
        if record_calls is not None:
            record_calls.append((table, records))
        record_set = set(records)
        return [
            row
            for row in tables[table]
            if row.get("_uuid") in record_set or row.get("name") in record_set
        ]

    def sb_list_rows(ctx, table):
        if sb_list_calls is not None:
            sb_list_calls.append(table)
        return tables[f"SB_{table}"]

    monkeypatch.setattr(
        router_health.ovn,
        "nbctl_list",
        list_rows,
    )
    monkeypatch.setattr(router_health.ovn, "nbctl_find", find_rows)
    monkeypatch.setattr(router_health.ovn, "nbctl_list_records", list_records)
    monkeypatch.setattr(router_health.ovn, "sbctl_list", sb_list_rows)


def test_audit_reports_corrupt_native_gateway_lsp(monkeypatch):
    conn, tables = native_state()
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 1
    assert "Backend: native OVN" in result.output
    assert "FAIL  gateway gw-1: LSP type" in result.output
    assert "FAIL  gateway gw-1: LSP addresses" in result.output
    assert "FAIL  gateway gw-1: router-port option" in result.output
    assert "FAIL  gateway gw-1: nat-addresses option" in result.output
    assert "FAIL  gateway gw-1: exclude-lb-vips-from-garp option" in result.output


def test_audit_reports_missing_peer_lsp_without_crashing(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["Logical_Switch_Port"] = []
    tables["Logical_Switch"][0]["ports"] = []
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 1
    assert "PASS  logical router: neutron-router-1" in result.output
    assert "FAIL  gateway gw-1: LSP attachment" in result.output
    assert "found no attachment" in result.output
    assert "list index out of range" not in result.output


def test_audit_reports_missing_uplink_localnet_lsp(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["Logical_Switch_Port"] = [
        row
        for row in tables["Logical_Switch_Port"]
        if row["name"] != "uplink-segment-1"
    ]
    tables["Logical_Switch"][0]["ports"].remove("uplink-lsp-uuid")
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 1
    assert (
        "PASS  gateway network net-1: uplink port intent: uplink-segment-1"
        in result.output
    )
    assert "FAIL  gateway uplink uplink-segment-1: LSP attachment" in result.output
    assert "found no attachment" in result.output


def test_audit_groups_gateway_and_internal_network_checks(monkeypatch):
    conn, tables = native_state(healthy=True)
    conn.network._ports.extend(
        [
            types.SimpleNamespace(
                id="int-1",
                name="",
                network_id="net-2",
                device_id="router-1",
                device_owner="network:router_interface",
                binding_host_id="",
            ),
            types.SimpleNamespace(
                id="uplink-port-2",
                name="uplink-segment-2",
                network_id="net-2",
                device_id="",
                device_owner="",
            ),
        ]
    )
    tables["Logical_Router"][0]["ports"].append("int-lrp-uuid")
    tables["Logical_Router_Port"].append({"_uuid": "int-lrp-uuid", "name": "lrp-int-1"})
    tables["Logical_Switch_Port"].extend(
        [
            {
                "_uuid": "int-lsp-uuid",
                "name": "int-1",
                "type": "router",
                "addresses": ["router"],
                "options": {"router-port": "lrp-int-1"},
            },
            {
                "_uuid": "uplink-lsp-uuid-2",
                "name": "uplink-segment-2",
                "type": "localnet",
                "addresses": ["unknown"],
                "tag": 1801,
                "options": {},
            },
        ]
    )
    tables["Logical_Switch"].append(
        {
            "_uuid": "ls-uuid-2",
            "name": "neutron-net-2",
            "ports": ["int-lsp-uuid", "uplink-lsp-uuid-2"],
        }
    )
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 0
    gateway_port = result.output.index("PASS  gateway gw-1: LRP attachment")
    gateway_uplink = result.output.index("PASS  gateway network net-1")
    internal_port = result.output.index("PASS  internal int-1: LRP attachment")
    internal_uplink = result.output.index("PASS  internal network net-2")
    assert gateway_port < gateway_uplink < internal_port < internal_uplink
    assert "PASS  gateway uplink uplink-segment-1: VLAN tag: 1800" in result.output
    assert "PASS  internal uplink uplink-segment-2: VLAN tag: 1801" in result.output


def test_audit_reports_missing_uplink_vlan_tag(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["Logical_Switch_Port"][1]["tag"] = []
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 1
    assert (
        "FAIL  gateway uplink uplink-segment-1: VLAN tag: "
        "expected one VLAN tag, found none" in result.output
    )


def test_audit_requires_one_router():
    result = runner.invoke(make_app(), ["router", "audit"])

    assert result.exit_code == 2
    assert "Missing argument 'NAME_OR_ID'" in result.output


def test_audit_accepts_requested_chassis_when_it_matches_binding(monkeypatch):
    conn, tables = native_state(healthy=True, requested_chassis="infra3.example.net")
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 0
    assert "PASS  gateway gw-1: requested-chassis: infra3.example.net" in result.output
    assert "FAIL" not in result.output


def test_audit_accepts_host_in_requested_chassis_list(monkeypatch):
    conn, tables = native_state(healthy=True, requested_chassis="infra3.example.net")
    tables["Logical_Switch_Port"][0]["options"]["requested-chassis"] = (
        "infra2.example.net,infra3.example.net"
    )
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 0
    assert "FAIL" not in result.output


def test_audit_scopes_router_rows_but_keeps_switch_membership(monkeypatch):
    conn, tables = native_state(healthy=True)
    list_calls = []
    find_calls = []
    record_calls = []
    patch_environment(
        monkeypatch,
        conn,
        tables,
        list_calls=list_calls,
        find_calls=find_calls,
        record_calls=record_calls,
    )

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 0
    assert list_calls == ["Logical_Switch"]
    assert {table for table, _condition in find_calls} == {
        "Logical_Router",
        "HA_Chassis_Group",
    }
    assert record_calls == [
        ("Logical_Router_Port", ["lrp-uuid"]),
        ("Logical_Switch_Port", ["gw-1", "uplink-segment-1"]),
    ]
    assert all("options:router-port" not in condition for _, condition in find_calls)


def test_audit_reports_empty_per_network_ha_chassis_group(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["HA_Chassis_Group"] = [
        {
            "_uuid": "network-hcg-uuid",
            "name": "neutron-net-1",
            "external_ids": {
                "neutron:network_id": "net-1",
                "neutron:router_id": "router-1",
            },
            "ha_chassis": [],
        }
    ]
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 1
    assert (
        "FAIL  per-network HA chassis group neutron-net-1: no HA_Chassis members"
        in result.output
    )
    assert "repopulation required" in result.output
    assert (
        "FAIL  HA chassis repopulation source: router HA chassis group "
        "neutron-router-1 is missing" in result.output
    )


def test_audit_reports_stale_only_per_network_ha_chassis_group(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["HA_Chassis_Group"] = [
        {
            "_uuid": "network-hcg-uuid",
            "name": "neutron-net-1",
            "external_ids": {
                "neutron:network_id": "net-1",
                "neutron:router_id": "router-1",
            },
            "ha_chassis": ["ha-uuid"],
        }
    ]
    tables["HA_Chassis"] = [
        {"_uuid": "ha-uuid", "chassis_name": "dead-chassis", "priority": 32767}
    ]
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 1
    assert "non-live members: dead-chassis" in result.output


def test_audit_accepts_live_per_network_ha_chassis_group(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["HA_Chassis_Group"] = [
        {
            "_uuid": "network-hcg-uuid",
            "name": "neutron-net-1",
            "external_ids": {
                "neutron:network_id": "net-1",
                "neutron:router_id": "router-1",
            },
            "ha_chassis": ["ha-uuid"],
        }
    ]
    tables["HA_Chassis"] = [
        {"_uuid": "ha-uuid", "chassis_name": "live-chassis", "priority": 32767}
    ]
    tables["SB_Chassis"] = [{"_uuid": "sb-uuid", "name": "live-chassis"}]
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 0
    assert (
        "PASS  per-network HA chassis group neutron-net-1: "
        "live members: live-chassis" in result.output
    )


def test_audit_loads_southbound_chassis_once(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["Logical_Router"][0]["options"] = {"chassis": "live-chassis"}
    tables["HA_Chassis_Group"] = [
        {
            "_uuid": "network-hcg-uuid",
            "name": "neutron-net-1",
            "external_ids": {
                "neutron:network_id": "net-1",
                "neutron:router_id": "router-1",
            },
            "ha_chassis": ["live-ha-uuid", "dead-ha-uuid"],
        }
    ]
    tables["HA_Chassis"] = [
        {"_uuid": "live-ha-uuid", "chassis_name": "live-chassis"},
        {"_uuid": "dead-ha-uuid", "chassis_name": "dead-chassis"},
    ]
    tables["SB_Chassis"] = [{"_uuid": "sb-uuid", "name": "live-chassis"}]
    sb_list_calls = []
    patch_environment(monkeypatch, conn, tables, sb_list_calls=sb_list_calls)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 0
    assert sb_list_calls == ["Chassis"]


def test_audit_uses_port_segment_for_expected_switch(monkeypatch):
    conn, tables = native_state(healthy=True)
    conn.network._ports[0].device_owner = "network:router_interface"
    tables["Logical_Switch_Port"][0]["external_ids"] = {
        "neutron:port_segment_id": "segment-1"
    }
    tables["Logical_Switch"][0]["name"] = "neutron-segment-1"
    tables["Logical_Switch"][0]["ports"] = ["lsp-uuid"]
    tables["Logical_Switch"].append(
        {
            "_uuid": "network-ls-uuid",
            "name": "neutron-net-1",
            "ports": ["uplink-lsp-uuid"],
        }
    )
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 0
    assert "attached to neutron-segment-1" in result.output


def test_audit_rejects_segment_placement_for_gateway(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["Logical_Switch_Port"][0]["external_ids"] = {
        "neutron:port_segment_id": "segment-1"
    }
    tables["Logical_Switch"][0]["name"] = "neutron-segment-1"
    patch_environment(monkeypatch, conn, tables)

    audit_result = runner.invoke(make_app(), ["router", "audit", "native-router"])
    repair_result = runner.invoke(make_app(), ["router", "repair", "native-router"])

    assert audit_result.exit_code == 1
    assert "FAIL  gateway gw-1: LSP attachment" in audit_result.output
    assert "expected neutron-net-1" in audit_result.output
    assert "found ['neutron-segment-1']" in audit_result.output
    assert repair_result.exit_code == 2
    assert "LSP attachment is invalid" in repair_result.output


def test_audit_reports_orphaned_attached_lrp_and_peer_lsp(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["Logical_Router"][0]["ports"].append("orphan-lrp-uuid")
    tables["Logical_Router_Port"].append(
        {"_uuid": "orphan-lrp-uuid", "name": "lrp-deleted-port"}
    )
    tables["Logical_Switch_Port"].append(
        {
            "_uuid": "orphan-lsp-uuid",
            "name": "deleted-port",
            "type": "router",
            "addresses": ["router"],
            "options": {"router-port": "lrp-deleted-port"},
        }
    )
    tables["Logical_Switch"][0]["ports"].append("orphan-lsp-uuid")
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])

    assert result.exit_code == 1
    assert "FAIL  orphaned LRP lrp-deleted-port" in result.output
    assert "FAIL  orphaned peer LSP deleted-port" in result.output


def test_repair_is_dry_run_and_preserves_unmanaged_options(monkeypatch):
    conn, tables = native_state(requested_chassis="infra3.example.net")
    patch_environment(monkeypatch, conn, tables)
    calls = []
    monkeypatch.setattr(
        router_health.ovn, "nbctl_raw", lambda ctx, args: calls.append(args)
    )

    result = runner.invoke(make_app(), ["router", "repair", "native-router"])

    assert result.exit_code == 0
    assert "Dry run only" in result.output
    assert "requested-chassis" not in result.output
    assert calls == []


def test_repair_applies_one_transaction_and_verifies(monkeypatch):
    conn, tables = native_state(requested_chassis="infra3.example.net")
    patch_environment(monkeypatch, conn, tables)
    calls = []

    def apply_repair(ctx, args):
        calls.append(args)
        lsp = tables["Logical_Switch_Port"][0]
        lsp["type"] = "router"
        lsp["addresses"] = ["router"]
        lsp["options"].update(
            {
                "router-port": "lrp-gw-1",
                "nat-addresses": "router",
                "exclude-lb-vips-from-garp": "true",
            }
        )

    monkeypatch.setattr(router_health.ovn, "nbctl_raw", apply_repair)

    result = runner.invoke(make_app(), ["router", "repair", "native-router", "--apply"])

    assert result.exit_code == 0
    assert (
        "Applied 1 LSP repair(s) and 0 HA chassis group repair(s); "
        "verification passed." in result.output
    )
    assert len(calls) == 1
    command = calls[0]
    assert "type=router" in command
    assert "addresses=router" in command
    assert "options:router-port=lrp-gw-1" in command
    assert all("requested-chassis" not in arg for arg in command)
    assert tables["Logical_Switch_Port"][0]["options"]["requested-chassis"] == (
        "infra3.example.net"
    )


def ha_repair_state():
    conn, tables = native_state(healthy=True)
    tables["Logical_Router"][0]["options"] = {"chassis": "live-chassis"}
    tables["HA_Chassis_Group"] = [
        {
            "_uuid": "network-ha-group-uuid",
            "name": "neutron-net-1",
            "external_ids": {
                "neutron:network_id": "net-1",
                "neutron:router_id": "router-1",
            },
            "ha_chassis": ["stale-ha-uuid"],
        }
    ]
    tables["HA_Chassis"] = [
        {
            "_uuid": "stale-ha-uuid",
            "chassis_name": "dead-chassis",
            "priority": 32767,
        }
    ]
    tables["SB_Chassis"] = [{"_uuid": "sb-uuid", "name": "live-chassis"}]
    return conn, tables


def test_repair_repopulates_per_network_ha_chassis_group(monkeypatch):
    conn, tables = ha_repair_state()
    patch_environment(monkeypatch, conn, tables)
    calls = []

    def apply_repair(ctx, args):
        calls.append(args)
        tables["HA_Chassis_Group"][0]["ha_chassis"] = ["new-ha-uuid"]
        tables["HA_Chassis"].append(
            {
                "_uuid": "new-ha-uuid",
                "chassis_name": "live-chassis",
                "priority": 32767,
            }
        )

    monkeypatch.setattr(router_health.ovn, "nbctl_raw", apply_repair)

    result = runner.invoke(make_app(), ["router", "repair", "native-router", "--apply"])

    assert result.exit_code == 0
    assert "remove non-live members: stale-ha-uuid" in result.output
    assert "repopulate with live chassis: live-chassis" in result.output
    assert (
        "Applied 0 LSP repair(s) and 1 HA chassis group repair(s); "
        "verification passed." in result.output
    )
    assert len(calls) == 1
    command = calls[0]
    assert "--if-exists" in command
    assert "remove" in command
    assert "stale-ha-uuid" in command
    assert "--id=@ha_chassis_0" in command
    assert "create" in command
    assert "chassis_name=live-chassis" in command
    assert "priority=32767" in command
    assert "add" in command
    assert "network-ha-group-uuid" in command


def test_repair_verification_requires_planned_ha_chassis_target(monkeypatch):
    conn, tables = ha_repair_state()
    tables["SB_Chassis"].append({"_uuid": "other-sb-uuid", "name": "other-live"})
    patch_environment(monkeypatch, conn, tables)

    def apply_wrong_target(ctx, args):
        tables["HA_Chassis_Group"][0]["ha_chassis"] = ["other-ha-uuid"]
        tables["HA_Chassis"].append(
            {
                "_uuid": "other-ha-uuid",
                "chassis_name": "other-live",
                "priority": 32767,
            }
        )

    monkeypatch.setattr(router_health.ovn, "nbctl_raw", apply_wrong_target)

    result = runner.invoke(make_app(), ["router", "repair", "native-router", "--apply"])

    assert result.exit_code == 1
    assert "ERROR: repair verification failed" in result.output
    assert "target chassis live-chassis is not a member" in result.output


def test_repair_verification_checks_removed_members_and_priority(monkeypatch):
    conn, tables = ha_repair_state()
    patch_environment(monkeypatch, conn, tables)

    def apply_incomplete_repair(ctx, args):
        tables["HA_Chassis_Group"][0]["ha_chassis"] = [
            "stale-ha-uuid",
            "new-ha-uuid",
        ]
        tables["HA_Chassis"].append(
            {
                "_uuid": "new-ha-uuid",
                "chassis_name": "live-chassis",
                "priority": 1,
            }
        )

    monkeypatch.setattr(router_health.ovn, "nbctl_raw", apply_incomplete_repair)

    result = runner.invoke(make_app(), ["router", "repair", "native-router", "--apply"])

    assert result.exit_code == 1
    assert "removed HA_Chassis references remain: stale-ha-uuid" in result.output
    assert "target chassis live-chassis has priority 1, expected 32767" in result.output


def test_repair_resolves_target_from_router_ha_chassis_group(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["HA_Chassis_Group"] = [
        {
            "_uuid": "network-ha-group-uuid",
            "name": "neutron-net-1",
            "external_ids": {
                "neutron:network_id": "net-1",
                "neutron:router_id": "router-1",
            },
            "ha_chassis": [],
        },
        {
            "_uuid": "router-ha-group-uuid",
            "name": "neutron-router-1",
            "external_ids": {"neutron:router_id": "router-1"},
            "ha_chassis": ["router-ha-uuid"],
        },
    ]
    tables["HA_Chassis"] = [
        {
            "_uuid": "router-ha-uuid",
            "chassis_name": "live-chassis",
            "priority": 32764,
        }
    ]
    tables["SB_Chassis"] = [{"_uuid": "sb-uuid", "name": "live-chassis"}]
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "repair", "native-router"])

    assert result.exit_code == 0
    assert "HA chassis group neutron-net-1" in result.output
    assert "repopulate with live chassis: live-chassis" in result.output
    assert "Dry run only" in result.output


def test_repair_refuses_unavailable_ha_chassis_target(monkeypatch):
    conn, tables = native_state(healthy=True)
    tables["Logical_Router"][0]["options"] = {"chassis": "dead-chassis"}
    tables["HA_Chassis_Group"] = [
        {
            "_uuid": "network-ha-group-uuid",
            "name": "neutron-net-1",
            "external_ids": {
                "neutron:network_id": "net-1",
                "neutron:router_id": "router-1",
            },
            "ha_chassis": [],
        }
    ]
    patch_environment(monkeypatch, conn, tables)
    calls = []
    monkeypatch.setattr(
        router_health.ovn, "nbctl_raw", lambda ctx, args: calls.append(args)
    )

    result = runner.invoke(make_app(), ["router", "repair", "native-router", "--apply"])

    assert result.exit_code == 2
    assert "options:chassis=dead-chassis is not live" in result.output
    assert "No changes made" in result.output
    assert calls == []


def test_unavailable_ha_target_does_not_block_lsp_repair(monkeypatch):
    conn, tables = native_state()
    tables["Logical_Router"][0]["options"] = {"chassis": "dead-chassis"}
    tables["HA_Chassis_Group"] = [
        {
            "_uuid": "network-ha-group-uuid",
            "name": "neutron-net-1",
            "external_ids": {
                "neutron:network_id": "net-1",
                "neutron:router_id": "router-1",
            },
            "ha_chassis": [],
        }
    ]
    patch_environment(monkeypatch, conn, tables)
    calls = []

    def apply_repair(ctx, args):
        calls.append(args)
        lsp = tables["Logical_Switch_Port"][0]
        lsp["type"] = "router"
        lsp["addresses"] = ["router"]
        lsp["options"].update(
            {
                "router-port": "lrp-gw-1",
                "nat-addresses": "router",
                "exclude-lb-vips-from-garp": "true",
            }
        )

    monkeypatch.setattr(router_health.ovn, "nbctl_raw", apply_repair)

    result = runner.invoke(make_app(), ["router", "repair", "native-router", "--apply"])

    assert result.exit_code == 2
    assert "REFUSED HA chassis group repair" in result.output
    assert "options:chassis=dead-chassis is not live" in result.output
    assert (
        "Applied 1 LSP repair(s) and 0 HA chassis group repair(s); "
        "verification passed." in result.output
    )
    assert "Some repair domains remain refused" in result.output
    assert len(calls) == 1
    assert "type=router" in calls[0]
    assert "create" not in calls[0]


def test_repair_refuses_wrong_switch_without_writing(monkeypatch):
    conn, tables = native_state()
    tables["Logical_Switch"][0]["name"] = "neutron-wrong-net"
    patch_environment(monkeypatch, conn, tables)
    calls = []
    monkeypatch.setattr(
        router_health.ovn, "nbctl_raw", lambda ctx, args: calls.append(args)
    )

    result = runner.invoke(make_app(), ["router", "repair", "native-router", "--apply"])

    assert result.exit_code == 2
    assert "REFUSED" in result.output
    assert "No changes made" in result.output
    assert calls == []


def test_repair_allows_segment_backed_switch(monkeypatch):
    conn, tables = native_state()
    conn.network._ports[0].device_owner = "network:router_interface"
    tables["Logical_Switch_Port"][0]["external_ids"] = {
        "neutron:port_segment_id": "segment-1"
    }
    tables["Logical_Switch"][0]["name"] = "neutron-segment-1"
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "repair", "native-router"])

    assert result.exit_code == 0
    assert "Dry run only" in result.output
    assert "REFUSED" not in result.output


@pytest.mark.parametrize(
    "device_owner",
    [
        "network:router_interface_distributed",
        "network:ha_router_replicated_interface",
        "network:router_ha_interface",
    ],
)
def test_audit_accepts_migrated_router_interface_owners(monkeypatch, device_owner):
    conn, tables = native_state(healthy=True)
    conn.network._ports[0].device_owner = device_owner
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "native-router"])
    repair_result = runner.invoke(make_app(), ["router", "repair", "native-router"])

    assert result.exit_code == 0
    assert repair_result.exit_code == 0
    assert "PASS  internal gw-1: LRP attachment" in result.output
    assert "orphaned LRP" not in result.output
    assert "No repairable differences found" in repair_result.output


def test_interface_audit_and_repair_exclude_gateway_options(monkeypatch):
    conn, tables = native_state()
    conn.network._ports[0].device_owner = "network:router_interface"
    patch_environment(monkeypatch, conn, tables)

    audit_result = runner.invoke(make_app(), ["router", "audit", "native-router"])
    repair_result = runner.invoke(make_app(), ["router", "repair", "native-router"])

    assert audit_result.exit_code == 1
    assert repair_result.exit_code == 0
    assert "FAIL  internal gw-1: LSP type" in audit_result.output
    assert "nat-addresses" not in repair_result.output
    assert "exclude-lb-vips-from-garp" not in repair_result.output


def flavored_state():
    test_router = types.SimpleNamespace(
        id="flavored-1", name="flavored-router", flavor_id="flavor-1"
    )
    tables = {
        "Logical_Router": [],
        "Logical_Router_Port": [],
        "Logical_Switch_Port": [],
        "Logical_Switch": [],
    }
    return FakeConnection(FakeNetwork(test_router, [])), tables


def test_audit_skips_flavored_router(monkeypatch):
    conn, tables = flavored_state()
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(make_app(), ["router", "audit", "flavored-router"])

    assert result.exit_code == 0
    assert "SKIP  router has flavor flavor-1" in result.output


def test_repair_refuses_flavored_router(monkeypatch):
    conn, tables = flavored_state()
    patch_environment(monkeypatch, conn, tables)

    result = runner.invoke(
        make_app(), ["router", "repair", "flavored-router", "--apply"]
    )

    assert result.exit_code == 2
    assert "REFUSED: router has flavor flavor-1" in result.output
