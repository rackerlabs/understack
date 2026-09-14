import typer
from typer.testing import CliRunner

from us_cli import kube
from us_cli.commands import backup
from us_cli.connection import ConnectionContext

runner = CliRunner()


def make_app(kube_context=None):
    app = typer.Typer()

    @app.callback()
    def main(ctx: typer.Context) -> None:
        ctx.obj = ConnectionContext(
            kube_context=kube_context,
            namespace="openstack",
            nb_pod="ovn-ovsdb-nb-0",
            sb_pod="ovn-ovsdb-sb-0",
            os_cloud=None,
        )

    backup.register(app)
    return app


def _fake_exec_to_file(recorded):
    def _inner(ctx, pod, container, argv, dest_path):
        recorded.append((pod, container, argv, dest_path))
        # write a placeholder so the size-report path has a real file
        with open(dest_path, "wb") as fh:
            fh.write(b"data")

    return _inner


def test_local_backs_up_mariadb_and_both_ovn_dbs(monkeypatch, tmp_path):
    recorded = []
    monkeypatch.setattr(kube, "exec_to_file", _fake_exec_to_file(recorded))
    # deterministic context slug + timestamp for filename assertions
    monkeypatch.setattr(
        backup, "resolve_kube_context", lambda c: "rax_prod_iad3_rxdb_mt"
    )
    monkeypatch.setattr(backup.time, "time", lambda: 1700000000)

    result = runner.invoke(
        make_app(), ["backup", "local", "--directory", str(tmp_path)]
    )
    assert result.exit_code == 0, result.output

    pods = [pod for pod, _c, _a, _d in recorded]
    assert pods == ["mariadb-0", "ovn-ovsdb-nb-0", "ovn-ovsdb-sb-0"]

    dests = [d for _p, _c, _a, d in recorded]
    slug = "rax-prod-iad3-rxdb-mt"
    assert dests[0].endswith(f"mariadb_backup_{slug}_1700000000.sql")
    assert dests[1].endswith(f"ovnnb_backup_{slug}_1700000000.db")
    assert dests[2].endswith(f"ovnsb_backup_{slug}_1700000000.db")


def test_local_ovn_uses_ovsdb_container_and_socket_paths(monkeypatch, tmp_path):
    recorded = []
    monkeypatch.setattr(kube, "exec_to_file", _fake_exec_to_file(recorded))

    result = runner.invoke(
        make_app(),
        ["backup", "local", "--directory", str(tmp_path), "--skip-mariadb"],
    )
    assert result.exit_code == 0, result.output

    nb = recorded[0]
    sb = recorded[1]
    assert nb[0] == "ovn-ovsdb-nb-0" and nb[1] == "ovsdb"
    assert nb[2] == ["ovsdb-client", "backup", "unix:/var/run/ovn/ovnnb_db.sock"]
    assert sb[0] == "ovn-ovsdb-sb-0" and sb[1] == "ovsdb"
    assert sb[2] == ["ovsdb-client", "backup", "unix:/var/run/ovn/ovnsb_db.sock"]


def test_local_mariadb_expands_password_inside_pod_not_locally(monkeypatch, tmp_path):
    recorded = []
    monkeypatch.setattr(kube, "exec_to_file", _fake_exec_to_file(recorded))

    result = runner.invoke(
        make_app(),
        ["backup", "local", "--directory", str(tmp_path), "--skip-ovn"],
    )
    assert result.exit_code == 0, result.output

    pod, container, argv, _dest = recorded[0]
    assert pod == "mariadb-0"
    # exec into the explicit mariadb container where the operator injects
    # $MARIADB_ROOT_PASSWORD
    assert container == "mariadb"
    # the command is a `sh -c` that expands the password env var *in the pod*,
    # so the secret value never appears in this process/kubectl argv
    assert argv[0] == "sh" and argv[1] == "-c"
    shell_cmd = argv[2]
    assert '"$MARIADB_ROOT_PASSWORD"' in shell_cmd
    assert "mariadb-dump" in shell_cmd
    assert "--all-databases" in shell_cmd
    # only the env-var *name* is present -- no decoded/literal password, and
    # no -p flag anywhere in the argv
    assert not any(a.startswith("-p") for a in argv)


def test_local_skip_both_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(kube, "exec_to_file", _fake_exec_to_file([]))
    result = runner.invoke(
        make_app(),
        [
            "backup",
            "local",
            "--directory",
            str(tmp_path),
            "--skip-mariadb",
            "--skip-ovn",
        ],
    )
    assert result.exit_code == 2


def test_local_surfaces_backup_exec_error(monkeypatch, tmp_path):
    def boom(ctx, pod, container, argv, dest_path):
        raise kube.BackupExecError("kaboom")

    monkeypatch.setattr(kube, "exec_to_file", boom)
    result = runner.invoke(
        make_app(),
        ["backup", "local", "--directory", str(tmp_path), "--skip-mariadb"],
    )
    assert result.exit_code == 1
    assert "kaboom" in result.output


def test_slug_sanitizes_non_alnum():
    assert backup._slug("rax_prod/iad3 dev") == "rax-prod-iad3-dev"
    assert backup._slug("") == "unknown"
    assert backup._slug("---") == "unknown"
