import subprocess

from us_net import connection
from us_net.connection import ConnectionContext
from us_net.connection import print_connection_banner
from us_net.connection import resolve_kube_context


def make_ctx(**overrides):
    defaults = dict(
        kube_context=None,
        namespace="openstack",
        nb_pod="ovn-ovsdb-nb-0",
        sb_pod="ovn-ovsdb-sb-0",
        os_cloud=None,
    )
    defaults.update(overrides)
    return ConnectionContext(**defaults)


def test_kubectl_base_without_context():
    assert make_ctx().kubectl_base() == ["kubectl"]


def test_kubectl_base_with_context():
    ctx = make_ctx(kube_context="my-ctx")
    assert ctx.kubectl_base() == ["kubectl", "--context", "my-ctx"]


def test_resolve_kube_context_prefers_explicit_value():
    assert resolve_kube_context("explicit") == "explicit"


def test_resolve_kube_context_falls_back_to_kubectl(monkeypatch):
    monkeypatch.setattr(
        connection.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd, 0, stdout="my-context\n", stderr=""
        ),
    )
    assert resolve_kube_context(None) == "my-context"


def test_print_connection_banner_without_openstack(monkeypatch, capsys):
    monkeypatch.setattr(
        connection, "resolve_kube_context", lambda kube_context: "ctx-1"
    )
    print_connection_banner(make_ctx(), include_openstack=False)
    out = capsys.readouterr().out
    assert "Kubernetes context : ctx-1" in out
    assert "OpenStack cloud" not in out


def test_print_connection_banner_with_openstack(monkeypatch, capsys):
    monkeypatch.setattr(
        connection, "resolve_kube_context", lambda kube_context: "ctx-1"
    )
    monkeypatch.setattr(
        connection.osclient,
        "describe_target",
        lambda os_cloud: [("auth URL", "https://example")],
    )
    ctx = make_ctx(os_cloud="dev-cloud")
    print_connection_banner(ctx, include_openstack=True)
    out = capsys.readouterr().out
    assert "OpenStack cloud    : dev-cloud" in out
    assert "auth URL" in out


def test_print_connection_banner_shows_default_label_when_cloud_unset(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        connection, "resolve_kube_context", lambda kube_context: "ctx-1"
    )
    monkeypatch.setattr(connection.osclient, "describe_target", lambda os_cloud: [])
    print_connection_banner(make_ctx(), include_openstack=True)
    out = capsys.readouterr().out
    assert "(default via OS_CLOUD / clouds.yaml)" in out
