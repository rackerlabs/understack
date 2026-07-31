import typer
from typer.testing import CliRunner

from us_net.commands import raw
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
            os_cloud=None,
        )

    raw.register(app)
    return app


def test_nbctl_execs_into_nb_pod_via_ovsdb_container(monkeypatch):
    calls = []

    def fake_stream_exec_in_pod(ctx, pod, container, argv):
        calls.append((pod, container, argv))
        return 0

    monkeypatch.setattr(raw.kube, "stream_exec_in_pod", fake_stream_exec_in_pod)
    result = runner.invoke(make_app(), ["nbctl", "--", "show"])
    assert result.exit_code == 0
    assert calls == [("ovn-ovsdb-nb-0", "ovsdb", ["ovn-nbctl", "show"])]


def test_nbctl_passes_through_flag_like_args_untouched(monkeypatch):
    calls = []
    monkeypatch.setattr(
        raw.kube,
        "stream_exec_in_pod",
        lambda ctx, pod, container, argv: calls.append(argv) or 0,
    )
    result = runner.invoke(
        make_app(), ["nbctl", "--", "--format=json", "list", "Chassis"]
    )
    assert result.exit_code == 0
    assert calls == [["ovn-nbctl", "--format=json", "list", "Chassis"]]


def test_nbctl_propagates_nonzero_exit_code(monkeypatch):
    monkeypatch.setattr(raw.kube, "stream_exec_in_pod", lambda *a, **k: 7)
    result = runner.invoke(make_app(), ["nbctl", "--", "show"])
    assert result.exit_code == 7


def test_sbctl_execs_into_sb_pod_via_ovsdb_container(monkeypatch):
    calls = []
    monkeypatch.setattr(
        raw.kube,
        "stream_exec_in_pod",
        lambda ctx, pod, container, argv: calls.append((pod, container)) or 0,
    )
    result = runner.invoke(make_app(), ["sbctl", "--", "list", "Chassis"])
    assert result.exit_code == 0
    assert calls == [("ovn-ovsdb-sb-0", "ovsdb")]


def test_vsctl_resolves_pod_by_node_with_ovn_controller_prefix(monkeypatch):
    resolve_calls = []
    exec_calls = []
    monkeypatch.setattr(
        raw.kube,
        "resolve_node_pod",
        lambda ctx, node, prefix, pod: (
            resolve_calls.append((node, prefix, pod)) or "resolved-pod"
        ),
    )
    monkeypatch.setattr(
        raw.kube,
        "stream_exec_in_pod",
        lambda ctx, pod, container, argv: (
            exec_calls.append((pod, container, argv)) or 0
        ),
    )
    result = runner.invoke(make_app(), ["vsctl", "--node", "node-1", "--", "show"])
    assert result.exit_code == 0
    assert resolve_calls == [("node-1", "ovn-controller", None)]
    assert exec_calls == [("resolved-pod", None, ["ovs-vsctl", "show"])]


def test_vsctl_explicit_pod_and_container_bypass_defaults(monkeypatch):
    resolve_calls = []
    exec_calls = []
    monkeypatch.setattr(
        raw.kube,
        "resolve_node_pod",
        lambda ctx, node, prefix, pod: resolve_calls.append(pod) or pod,
    )
    monkeypatch.setattr(
        raw.kube,
        "stream_exec_in_pod",
        lambda ctx, pod, container, argv: exec_calls.append((pod, container)) or 0,
    )
    result = runner.invoke(
        make_app(),
        [
            "vsctl",
            "--node",
            "node-1",
            "--pod",
            "my-pod",
            "--container",
            "my-c",
            "--",
            "show",
        ],
    )
    assert result.exit_code == 0
    assert resolve_calls == ["my-pod"]
    assert exec_calls == [("my-pod", "my-c")]


def test_appctl_default_target_prefix_is_ovn_controller(monkeypatch):
    resolve_calls = []
    monkeypatch.setattr(
        raw.kube,
        "resolve_node_pod",
        lambda ctx, node, prefix, pod: resolve_calls.append(prefix) or "pod-x",
    )
    monkeypatch.setattr(raw.kube, "stream_exec_in_pod", lambda *a, **k: 0)
    result = runner.invoke(make_app(), ["appctl", "--node", "node-1", "--", "version"])
    assert result.exit_code == 0
    assert resolve_calls == ["ovn-controller"]


def test_appctl_custom_target_prefix(monkeypatch):
    resolve_calls = []
    monkeypatch.setattr(
        raw.kube,
        "resolve_node_pod",
        lambda ctx, node, prefix, pod: resolve_calls.append(prefix) or "pod-x",
    )
    monkeypatch.setattr(raw.kube, "stream_exec_in_pod", lambda *a, **k: 0)
    result = runner.invoke(
        make_app(),
        ["appctl", "--node", "node-1", "--target", "openvswitch", "--", "version"],
    )
    assert result.exit_code == 0
    assert resolve_calls == ["openvswitch"]
