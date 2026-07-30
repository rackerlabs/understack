from typer.testing import CliRunner

from us_net.cli import app

runner = CliRunner()


def test_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("nbctl", "sbctl", "vsctl", "appctl", "router"):
        assert command in result.output


def test_bare_invocation_shows_usage_instead_of_missing_command_error():
    result = runner.invoke(app, [])
    assert "Usage:" in result.output
    for command in ("nbctl", "sbctl", "vsctl", "appctl", "router"):
        assert command in result.output
    assert "Missing command" not in result.output


def test_bare_router_shows_usage_instead_of_missing_command_error():
    result = runner.invoke(app, ["router"])
    assert "Usage:" in result.output
    assert "show" in result.output
    assert "Missing command" not in result.output


def test_callback_builds_connection_context(monkeypatch):
    import us_net.commands.raw as raw

    captured = {}
    monkeypatch.setattr(
        raw.kube,
        "stream_exec_in_pod",
        lambda ctx, pod, container, argv: captured.setdefault("ctx", ctx) and 0,
    )
    result = runner.invoke(
        app,
        [
            "--context",
            "my-ctx",
            "--namespace",
            "my-ns",
            "--nb-pod",
            "my-nb-pod",
            "--os-cloud",
            "my-cloud",
            "nbctl",
            "--",
            "show",
        ],
    )
    assert result.exit_code == 0
    ctx = captured["ctx"]
    assert ctx.kube_context == "my-ctx"
    assert ctx.namespace == "my-ns"
    assert ctx.nb_pod == "my-nb-pod"
    assert ctx.os_cloud == "my-cloud"
