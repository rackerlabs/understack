import types

import pytest
import typer
from typer.testing import CliRunner

from us_cli.commands import trunk
from us_cli.connection import ConnectionContext

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

    app.add_typer(trunk.app, name="trunk")
    return app


def make_parent(vnic_type="baremetal", bound=True):
    return types.SimpleNamespace(
        id="parent-1",
        device_owner="compute:ironic",
        binding_vnic_type=vnic_type,
        binding_vif_type="other" if bound else "unbound",
        binding_profile={"physical_network": "f20-1-network"} if bound else {},
    )


def make_subport(profile=None, device_owner=trunk.SUBPORT_DEVICE_OWNER):
    """A subport port, by default already in the state we want."""
    return types.SimpleNamespace(
        id="sub-1",
        name="subport",
        device_owner=device_owner,
        binding_vnic_type="normal",
        binding_vif_type="unbound",
        binding_profile={} if profile is None else profile,
    )


def make_trunk(status="ACTIVE"):
    return types.SimpleNamespace(
        id="trunk-1",
        name="bm-trunk",
        port_id="parent-1",
        status=status,
        sub_ports=[
            {"port_id": "sub-1", "segmentation_type": "vlan", "segmentation_id": 1500}
        ],
    )


class FakeNetworkAPI:
    def __init__(self, trunks, ports):
        self._trunks = trunks
        self._ports = {port.id: port for port in ports}
        self.updates: list[tuple[str, dict]] = []
        self.reflect_updates = True

    def trunks(self):
        return list(self._trunks)

    def find_trunk(self, name_or_id):
        for item in self._trunks:
            if name_or_id in (item.id, item.name):
                return item
        return None

    def get_port(self, port_id):
        return self._ports[port_id]

    def update_port(self, port_id, **attrs):
        self.updates.append((port_id, attrs))
        port = self._ports[port_id]
        if self.reflect_updates:
            for key, value in attrs.items():
                setattr(port, key, value)
        return port


class FakeConfig:
    config = {}


class FakeConnection:
    def __init__(self, trunks, ports):
        self.network = FakeNetworkAPI(trunks, ports)
        self.config = FakeConfig()


class FakeNb:
    """The NB Logical_Switch_Port rows, keyed by port id."""

    def __init__(self, rows):
        self.rows = rows
        self.calls: list[list[str]] = []

    def list_records(self, ctx, table, records):
        assert table == "Logical_Switch_Port"
        return [
            {"name": port_id, **columns}
            for port_id, columns in self.rows.items()
            if port_id in records
        ]

    def raw(self, ctx, args):
        self.calls.append(args)
        for index, arg in enumerate(args):
            # `-- clear Logical_Switch_Port <port> <column>`
            if arg == "clear":
                port_id, column = args[index + 2], args[index + 3]
                self.rows.get(port_id, {}).pop(column, None)
        return ""


@pytest.fixture
def setup(monkeypatch):
    def _setup(trunks=None, ports=None, nb_rows=None):
        trunks = [make_trunk()] if trunks is None else trunks
        ports = [make_parent(), make_subport()] if ports is None else ports
        conn = FakeConnection(trunks, ports)
        nb = FakeNb({} if nb_rows is None else nb_rows)
        monkeypatch.setattr(trunk.osclient, "get_connection", lambda os_cloud: conn)
        monkeypatch.setattr(trunk.ovn, "nbctl_list_records", nb.list_records)
        monkeypatch.setattr(trunk.ovn, "nbctl_raw", nb.raw)
        return conn, nb

    return _setup


STALE_PROFILE = {"parent_name": "parent-1", "tag": 1500}
STALE_LSP = {"sub-1": {"parent_name": "parent-1", "tag_request": 1500}}


class TestAudit:
    def test_a_clean_trunk_passes(self, setup):
        setup(nb_rows={"sub-1": {"parent_name": "", "tag_request": []}})

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert "FAIL" not in result.output
        assert "Trunk bm-trunk (trunk-1)" in result.output

    def test_stale_profile_and_lsp_rows_fail(self, setup):
        setup(
            ports=[make_parent(), make_subport(profile=dict(STALE_PROFILE))],
            nb_rows={"sub-1": dict(STALE_LSP["sub-1"])},
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "stale ml2/ovn keys: parent_name, tag" in result.output
        assert "still set: parent_name, tag_request" in result.output

    def test_a_status_that_disagrees_with_the_parent_fails(self, setup):
        setup(trunks=[make_trunk(status="DOWN")])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "expected ACTIVE for a bound parent, found DOWN" in result.output

    def test_an_unbound_parent_expects_a_down_trunk(self, setup):
        setup(
            trunks=[make_trunk(status="DOWN")],
            ports=[make_parent(bound=False), make_subport()],
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert "trunk status: DOWN" in result.output

    def test_a_non_baremetal_trunk_is_skipped(self, setup):
        setup(ports=[make_parent(vnic_type="normal"), make_subport()])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert "so ml2/ovn still owns this trunk" in result.output
        assert "(no baremetal trunks found)" in result.output

    def test_an_unclaimed_subport_fails(self, setup):
        setup(ports=[make_parent(), make_subport(device_owner="")])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "expected trunk:subport, found (empty)" in result.output

    def test_an_unknown_trunk_errors(self, setup):
        setup()

        result = runner.invoke(make_app(), ["trunk", "audit", "nope"])

        assert result.exit_code == 1
        assert "trunk 'nope' not found" in result.output


class TestRepair:
    def test_a_dry_run_changes_nothing(self, setup):
        conn, nb = setup(
            ports=[make_parent(), make_subport(profile=dict(STALE_PROFILE))],
            nb_rows={"sub-1": dict(STALE_LSP["sub-1"])},
        )

        result = runner.invoke(make_app(), ["trunk", "repair"])

        assert result.exit_code == 0, result.output
        assert "binding profile: drop parent_name, tag" in result.output
        assert "Dry run only" in result.output
        assert conn.network.updates == []
        assert nb.calls == []

    def test_apply_strips_the_profile_and_clears_the_lsp(self, setup):
        conn, nb = setup(
            ports=[
                make_parent(),
                make_subport(profile={**STALE_PROFILE, "keep": "me"}),
            ],
            nb_rows={"sub-1": dict(STALE_LSP["sub-1"])},
        )

        result = runner.invoke(make_app(), ["trunk", "repair", "--apply"])

        assert result.exit_code == 0, result.output
        assert conn.network.updates == [("sub-1", {"binding_profile": {"keep": "me"}})]
        assert nb.rows == {"sub-1": {}}
        assert "Repaired 1 subport(s); verification passed." in result.output

    def test_apply_reclaims_an_unclaimed_subport(self, setup):
        conn, _ = setup(ports=[make_parent(), make_subport(device_owner="")])

        result = runner.invoke(make_app(), ["trunk", "repair", "--apply"])

        assert result.exit_code == 0, result.output
        assert conn.network.updates == [
            ("sub-1", {"device_owner": trunk.SUBPORT_DEVICE_OWNER})
        ]

    def test_apply_clears_an_lsp_whose_profile_is_already_clean(self, setup):
        conn, nb = setup(nb_rows={"sub-1": dict(STALE_LSP["sub-1"])})

        result = runner.invoke(make_app(), ["trunk", "repair", "--apply"])

        assert result.exit_code == 0, result.output
        assert conn.network.updates == []
        assert nb.rows == {"sub-1": {}}
        assert "cleared in the NB directly: sub-1: parent_name" in result.output

    def test_a_clean_trunk_needs_no_repair(self, setup):
        conn, nb = setup()

        result = runner.invoke(make_app(), ["trunk", "repair", "--apply"])

        assert result.exit_code == 0, result.output
        assert "No leftover ml2/ovn trunk state found." in result.output
        assert conn.network.updates == []
        assert nb.calls == []

    def test_verification_failure_exits_nonzero(self, setup):
        conn, _ = setup(
            ports=[make_parent(), make_subport(profile=dict(STALE_PROFILE))]
        )
        # A Neutron update that silently does not stick.
        conn.network.reflect_updates = False

        result = runner.invoke(make_app(), ["trunk", "repair", "--apply"])

        assert result.exit_code == 1
        assert "repair verification failed" in result.output
        assert "sub-1: binding profile: drop parent_name, tag" in result.output
