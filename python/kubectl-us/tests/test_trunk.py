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
        binding_host_id="node-1" if bound else "",
        binding_vnic_type=vnic_type,
        binding_vif_type="other" if bound else "unbound",
        binding_profile={"physical_network": "f20-1-network"} if bound else {},
    )


TRUNK_PROFILE = {"parent_name": "parent-1", "tag": 1500}


def make_subport(
    profile=None,
    device_owner=trunk.SUBPORT_DEVICE_OWNER,
    status="ACTIVE",
    vif_type="other",
    description="",
):
    """A subport port, by default already in the state we want."""
    profile = dict(TRUNK_PROFILE) if profile is None else profile
    return types.SimpleNamespace(
        id="sub-1",
        name="subport",
        status=status,
        description=description,
        device_owner=device_owner,
        binding_vnic_type="normal",
        binding_vif_type=vif_type,
        binding_profile=profile,
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
        self.port_queries: list[list[str]] = []

    def trunks(self):
        return list(self._trunks)

    def find_trunk(self, name_or_id):
        for item in self._trunks:
            if name_or_id in (item.id, item.name):
                return item
        return None

    def get_trunk(self, trunk_id):
        return next(item for item in self._trunks if item.id == trunk_id)

    def ports(self, id=None):
        self.port_queries.append(id)
        return [self._ports[port_id] for port_id in id if port_id in self._ports]

    def update_port(self, port_id, **attrs):
        self.updates.append((port_id, attrs))
        return self._ports[port_id]


class FakeConfig:
    config = {}


class FakeConnection:
    def __init__(self, trunks, ports):
        self.network = FakeNetworkAPI(trunks, ports)
        self.config = FakeConfig()


@pytest.fixture
def setup(monkeypatch):
    def _setup(trunks=None, ports=None):
        trunks = [make_trunk()] if trunks is None else trunks
        ports = [make_parent(), make_subport()] if ports is None else ports
        conn = FakeConnection(trunks, ports)
        monkeypatch.setattr(trunk.osclient, "get_connection", lambda os_cloud: conn)
        return conn

    return _setup


class TestAudit:
    def test_a_clean_trunk_passes(self, setup):
        setup()

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert "FAIL" not in result.output
        assert "Trunk bm-trunk (trunk-1)" in result.output

    def test_a_missing_profile_fails(self, setup):
        setup(
            ports=[make_parent(), make_subport(profile={})],
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert (
            "expected parent_name=parent-1, tag=1500; "
            "found parent_name=None, tag=None" in result.output
        )

    def test_a_profile_that_disagrees_with_the_trunk_fails(self, setup):
        setup(
            ports=[
                make_parent(),
                make_subport(profile={"parent_name": "parent-1", "tag": 1600}),
            ]
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "expected tag=1500; found tag=1600" in result.output

    def test_a_status_that_disagrees_with_the_parent_fails(self, setup):
        setup(trunks=[make_trunk(status="DOWN")])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "expected ACTIVE for a bound parent, found DOWN" in result.output

    def test_an_unbound_parent_expects_a_down_trunk(self, setup):
        setup(
            trunks=[make_trunk(status="DOWN")],
            ports=[
                make_parent(bound=False),
                make_subport(status="DOWN", vif_type="unbound"),
            ],
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert "trunk status: DOWN" in result.output

    def test_a_subport_status_that_disagrees_with_the_parent_fails(self, setup):
        setup(ports=[make_parent(), make_subport(status="DOWN")])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "subport sub-1: status" in result.output
        assert "expected ACTIVE for a bound parent, found DOWN" in result.output

    def test_a_non_baremetal_trunk_is_skipped(self, setup):
        setup(ports=[make_parent(vnic_type="normal"), make_subport()])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert "so ml2/ovn still owns this trunk" in result.output
        assert "(no baremetal trunks found)" in result.output

    def test_a_non_trunk_owned_subport_is_out_of_scope(self, setup):
        setup(
            ports=[
                make_parent(),
                make_subport(
                    profile={},
                    device_owner="network:router_interface",
                    status="DOWN",
                    vif_type="ovs",
                ),
            ],
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert "SKIP  subport sub-1" in result.output
        assert "device_owner=network:router_interface" in result.output

    def test_an_ovs_bound_trunk_subport_fails(self, setup):
        setup(ports=[make_parent(), make_subport(vif_type="ovs")])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "binding vif_type: expected other, found ovs" in result.output

    def test_an_unbound_subport_under_a_bound_parent_fails(self, setup):
        setup(ports=[make_parent(), make_subport(vif_type="unbound")])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "binding vif_type: expected other, found unbound" in result.output

    def _second_trunk(self):
        parent = make_parent()
        parent.id = "parent-2"
        subport = make_subport()
        subport.id = "sub-2"
        subport.binding_profile = {"parent_name": "parent-2", "tag": 1500}
        second = make_trunk()
        second.id = "trunk-2"
        second.name = "other-trunk"
        second.port_id = "parent-2"
        second.sub_ports = [
            {"port_id": "sub-2", "segmentation_type": "vlan", "segmentation_id": 1500}
        ]
        return second, parent, subport

    def test_the_subports_of_an_ovn_trunk_are_not_fetched(self, setup):
        conn = setup(ports=[make_parent(vnic_type="normal"), make_subport()])

        runner.invoke(make_app(), ["trunk", "audit"])

        assert conn.network.port_queries == [["parent-1"]]

    def test_ports_are_fetched_in_chunks(self, setup, monkeypatch):
        monkeypatch.setattr(trunk, "PORT_QUERY_CHUNK", 3)
        second, parent, subport = self._second_trunk()
        third, third_parent, third_subport = self._second_trunk()
        third.id, third.port_id = "trunk-3", "parent-3"
        third.sub_ports = [{"port_id": "sub-3", "segmentation_id": 1500}]
        third_parent.id, third_subport.id = "parent-3", "sub-3"
        third_subport.binding_profile = {"parent_name": "parent-3", "tag": 1500}
        conn = setup(
            trunks=[make_trunk(), second, third],
            ports=[
                make_parent(),
                make_subport(),
                parent,
                subport,
                third_parent,
                third_subport,
            ],
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert conn.network.port_queries == [
            ["parent-1", "parent-2", "parent-3"],
            ["sub-1", "sub-2", "sub-3"],
        ]

    def test_a_missing_subport_fails_only_its_trunk(self, setup):
        second, parent, subport = self._second_trunk()
        setup(
            trunks=[make_trunk(), second],
            ports=[make_parent(), parent, subport],
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "subport sub-1: port not found" in result.output
        assert "Trunk other-trunk (trunk-2)" in result.output
        assert "FAIL  subport sub-2" not in result.output

    def test_a_missing_parent_fails_only_its_trunk(self, setup):
        second, parent, subport = self._second_trunk()
        setup(trunks=[make_trunk(), second], ports=[parent, subport])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "FAIL  trunk bm-trunk (trunk-1): parent port parent-1 not found" in (
            result.output
        )
        assert "Trunk other-trunk (trunk-2)" in result.output

    def test_an_unknown_trunk_errors(self, setup):
        setup()

        result = runner.invoke(make_app(), ["trunk", "audit", "nope"])

        assert result.exit_code == 1
        assert "trunk 'nope' not found" in result.output


class TestAuditFix:
    def test_drifted_subport_bindings_name_the_reattach_step(self, setup):
        conn = setup(ports=[make_parent(), make_subport(profile={})])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert (
            "openstack baremetal node service node-1 --service-steps "
            """'[{"interface": "network", "step": "reattach_networking"}]'"""
        ) in result.output
        assert conn.network.updates == []

    @pytest.mark.parametrize("vif_type", ["ovs", "unbound"])
    def test_a_wrong_vif_type_names_the_reattach_step(self, setup, vif_type):
        setup(ports=[make_parent(), make_subport(vif_type=vif_type)])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "reattach_networking" in result.output

    def test_an_unbound_parent_has_no_node_to_reattach(self, setup):
        setup(
            trunks=[make_trunk(status="DOWN")],
            ports=[
                make_parent(bound=False),
                make_subport(status="DOWN", vif_type="ovs"),
            ],
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "there is no node to reattach" in result.output
        assert "reattach_networking" not in result.output

    def test_a_status_mismatch_alone_names_no_fix(self, setup):
        setup(trunks=[make_trunk(status="DOWN")])

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 1
        assert "reattach_networking" not in result.output
        assert "no node to reattach" not in result.output

    def test_a_non_trunk_owner_names_no_fix(self, setup):
        setup(
            ports=[
                make_parent(),
                make_subport(
                    profile={},
                    device_owner="network:router_gateway",
                    vif_type="ovs",
                ),
            ],
        )

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert "reattach_networking" not in result.output

    def test_a_clean_trunk_names_no_fix(self, setup):
        setup()

        result = runner.invoke(make_app(), ["trunk", "audit"])

        assert result.exit_code == 0, result.output
        assert "reattach_networking" not in result.output
