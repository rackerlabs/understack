import json
import subprocess

import pytest

from us_cli import kube
from us_cli.connection import ConnectionContext


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


def test_exec_argv_without_context_or_container():
    argv = kube._exec_argv(make_ctx(), "mypod", None, ["ovn-nbctl", "show"])
    assert argv == [
        "kubectl",
        "exec",
        "-n",
        "openstack",
        "mypod",
        "--",
        "ovn-nbctl",
        "show",
    ]


def test_exec_argv_with_context_and_container():
    ctx = make_ctx(kube_context="my-ctx")
    argv = kube._exec_argv(ctx, "mypod", "ovsdb", ["ovn-nbctl", "show"])
    assert argv == [
        "kubectl",
        "--context",
        "my-ctx",
        "exec",
        "-n",
        "openstack",
        "mypod",
        "-c",
        "ovsdb",
        "--",
        "ovn-nbctl",
        "show",
    ]


def test_exec_in_pod_runs_subprocess_and_captures_output(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(kube.subprocess, "run", fake_run)
    result = kube.exec_in_pod(make_ctx(), "mypod", "ovsdb", ["ovn-nbctl", "show"])
    assert result.stdout == "ok"
    assert captured["kwargs"] == {"capture_output": True, "text": True}
    assert captured["cmd"][-2:] == ["ovn-nbctl", "show"]


def test_stream_exec_in_pod_returns_returncode(monkeypatch):
    monkeypatch.setattr(
        kube.subprocess, "run", lambda cmd: subprocess.CompletedProcess(cmd, 3)
    )
    assert kube.stream_exec_in_pod(make_ctx(), "mypod", None, ["ovn-nbctl"]) == 3


def test_pods_on_node_filters_by_node_and_prefix(monkeypatch):
    payload = {
        "items": [
            {
                "metadata": {"name": "ovn-controller-default-abc"},
                "spec": {"nodeName": "node-1"},
            },
            {
                "metadata": {"name": "ovn-controller-default-xyz"},
                "spec": {"nodeName": "node-2"},
            },
            {
                "metadata": {"name": "neutron-server-abc"},
                "spec": {"nodeName": "node-1"},
            },
        ]
    }
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps(payload), stderr=""
        ),
    )
    pods = kube.pods_on_node(make_ctx(), "node-1", "ovn-controller")
    assert pods == ["ovn-controller-default-abc"]


def test_pods_on_node_exits_on_kubectl_failure(monkeypatch):
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="boom"
        ),
    )
    with pytest.raises(SystemExit):
        kube.pods_on_node(make_ctx(), "node-1", "ovn-controller")


def test_resolve_node_pod_returns_explicit_pod_without_lookup(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("should not call pods_on_node when --pod is given")

    monkeypatch.setattr(kube, "pods_on_node", fail)
    pod = kube.resolve_node_pod(make_ctx(), "node-1", "ovn-controller", "explicit-pod")
    assert pod == "explicit-pod"


def test_resolve_node_pod_returns_single_candidate(monkeypatch):
    monkeypatch.setattr(kube, "pods_on_node", lambda ctx, node, prefix: ["only-one"])
    pod = kube.resolve_node_pod(make_ctx(), "node-1", "ovn-controller", None)
    assert pod == "only-one"


def test_resolve_node_pod_exits_on_no_candidates(monkeypatch):
    monkeypatch.setattr(kube, "pods_on_node", lambda ctx, node, prefix: [])
    with pytest.raises(SystemExit):
        kube.resolve_node_pod(make_ctx(), "node-1", "ovn-controller", None)


def test_resolve_node_pod_exits_on_multiple_candidates(monkeypatch):
    monkeypatch.setattr(kube, "pods_on_node", lambda ctx, node, prefix: ["a", "b"])
    with pytest.raises(SystemExit):
        kube.resolve_node_pod(make_ctx(), "node-1", "ovn-controller", None)


def test_exec_to_file_writes_stdout_and_uses_dash_i(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        # emulate kubectl streaming bytes to the redirected stdout file
        kwargs["stdout"].write(b"backup-bytes")
        return subprocess.CompletedProcess(cmd, 0, stderr=b"")

    monkeypatch.setattr(kube.subprocess, "run", fake_run)
    dest = tmp_path / "out.db"
    kube.exec_to_file(
        make_ctx(),
        "ovn-ovsdb-nb-0",
        "ovsdb",
        ["ovsdb-client", "backup", "unix:/x.sock"],
        str(dest),
    )
    assert dest.read_bytes() == b"backup-bytes"
    # a clean run leaves only the final file, no leftover temp/partial file
    assert list(tmp_path.iterdir()) == [dest]
    # -i must be present, -t must NOT be (a TTY corrupts the byte stream)
    assert "-i" in captured["cmd"]
    assert "-t" not in captured["cmd"]
    assert captured["cmd"][-3:] == ["ovsdb-client", "backup", "unix:/x.sock"]


def test_exec_to_file_raises_backup_exec_error_on_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        kube.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, stderr=b"nope"),
    )
    with pytest.raises(kube.BackupExecError, match="nope"):
        kube.exec_to_file(make_ctx(), "pod", None, ["cmd"], str(tmp_path / "x"))


def test_exec_to_file_failure_creates_no_final_file_and_leaves_no_temp(
    monkeypatch, tmp_path
):
    # even after writing partial bytes, a nonzero exit must not leave a file
    def fake_run(cmd, **kwargs):
        kwargs["stdout"].write(b"partial-junk")
        return subprocess.CompletedProcess(cmd, 1, stderr=b"boom")

    monkeypatch.setattr(kube.subprocess, "run", fake_run)
    dest = tmp_path / "backup.db"
    with pytest.raises(kube.BackupExecError):
        kube.exec_to_file(make_ctx(), "pod", None, ["cmd"], str(dest))

    assert not dest.exists()
    # no leftover temp/partial files in the destination directory
    assert list(tmp_path.iterdir()) == []


def test_exec_to_file_failure_does_not_clobber_existing_backup(monkeypatch, tmp_path):
    dest = tmp_path / "backup.db"
    dest.write_bytes(b"previous-good-backup")

    def fake_run(cmd, **kwargs):
        kwargs["stdout"].write(b"partial-junk")
        return subprocess.CompletedProcess(cmd, 1, stderr=b"boom")

    monkeypatch.setattr(kube.subprocess, "run", fake_run)
    with pytest.raises(kube.BackupExecError):
        kube.exec_to_file(make_ctx(), "pod", None, ["cmd"], str(dest))

    # the pre-existing backup is untouched, and no temp file lingers
    assert dest.read_bytes() == b"previous-good-backup"
    assert list(tmp_path.iterdir()) == [dest]


def test_exec_to_file_failure_to_spawn_leaves_no_temp(monkeypatch, tmp_path):
    # a raised exception (e.g. kubectl not found) must also clean up the temp
    def raise_oserror(cmd, **kwargs):
        raise OSError("kubectl not found")

    monkeypatch.setattr(kube.subprocess, "run", raise_oserror)
    dest = tmp_path / "backup.db"
    with pytest.raises(OSError, match="kubectl not found"):
        kube.exec_to_file(make_ctx(), "pod", None, ["cmd"], str(dest))

    assert not dest.exists()
    assert list(tmp_path.iterdir()) == []
