"""kubectl exec/get wrappers used by the raw passthrough and higher-level commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

from us_cli.connection import ConnectionContext


def _exec_argv(
    ctx: ConnectionContext, pod: str, container: str | None, argv: list[str]
) -> list[str]:
    cmd = ctx.kubectl_base() + ["exec", "-n", ctx.namespace, pod]
    if container:
        cmd += ["-c", container]
    cmd += ["--", *argv]
    return cmd


def exec_in_pod(
    ctx: ConnectionContext, pod: str, container: str | None, argv: list[str]
) -> subprocess.CompletedProcess:
    """Run `kubectl exec` in a pod and capture its output."""
    return subprocess.run(
        _exec_argv(ctx, pod, container, argv), capture_output=True, text=True
    )


def stream_exec_in_pod(
    ctx: ConnectionContext, pod: str, container: str | None, argv: list[str]
) -> int:
    """Run `kubectl exec` with stdout/stderr inherited, for raw passthrough commands."""
    result = subprocess.run(_exec_argv(ctx, pod, container, argv))
    return result.returncode


def exec_to_file(
    ctx: ConnectionContext,
    pod: str,
    container: str | None,
    argv: list[str],
    dest_path: str,
) -> None:
    """Run `kubectl exec -i` and stream its stdout into a local file.

    Used for the backup commands, which produce binary/large output on
    stdout that we redirect to a file exactly like the documented
    `kubectl ... exec -i ... > file` runbook commands. `-i` (and the
    deliberate absence of `-t`) matters here: a TTY corrupts the
    ovsdb-client/mariadb-dump byte stream, so it's never allocated.

    stderr is captured and included in the raised error on failure so the
    caller can surface why kubectl/the in-pod command failed.
    """
    cmd = ctx.kubectl_base() + ["exec", "-i", "-n", ctx.namespace, pod]
    if container:
        cmd += ["-c", container]
    cmd += ["--", *argv]

    dest = os.fspath(dest_path)
    dest_dir = os.path.dirname(dest) or "."
    # Stream into a uniquely named temp file in the *same* directory (so the
    # final os.replace is an atomic rename, not a cross-filesystem copy), and
    # only move it into place after a clean exit. This way a failed/partial
    # run never leaves a truncated file under the real name, and never
    # clobbers an existing same-name backup.
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=dest_dir, prefix=os.path.basename(dest) + ".", suffix=".partial"
    )
    try:
        with os.fdopen(tmp_fd, "wb") as tmp:
            result = subprocess.run(cmd, stdout=tmp, stderr=subprocess.PIPE)
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace").strip()
            raise BackupExecError(
                f"kubectl exec into {pod} failed (exit {result.returncode}):\n{stderr}"
            )
        os.replace(tmp_path, dest)
    except BaseException:
        # Any failure -- nonzero exit, a raised exception, or an interrupt --
        # must remove the temp file and leave any existing destination intact.
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


class BackupExecError(RuntimeError):
    """Raised when a `kubectl exec` backup stream fails."""


def pods_on_node(ctx: ConnectionContext, node_name: str, name_prefix: str) -> list[str]:
    """Pod names in ctx.namespace on node_name whose name starts with name_prefix."""
    cmd = ctx.kubectl_base() + ["get", "pods", "-n", ctx.namespace, "-o", "json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"ERROR: kubectl get pods failed:\n{result.stderr.strip()}", file=sys.stderr
        )
        sys.exit(1)
    pods = json.loads(result.stdout)
    return [
        item["metadata"]["name"]
        for item in pods.get("items", [])
        if item.get("spec", {}).get("nodeName") == node_name
        and item["metadata"]["name"].startswith(name_prefix)
    ]


def resolve_node_pod(
    ctx: ConnectionContext, node_name: str, name_prefix: str, explicit_pod: str | None
) -> str:
    """Resolve the single pod to exec into for a node-targeted command.

    The DaemonSet pod naming comes from the upstream openstack-helm chart,
    not anything vendored in this repo, so name_prefix may not match every
    deployment -- explicit_pod (--pod) is the escape hatch when it's wrong.
    """
    if explicit_pod:
        return explicit_pod
    candidates = pods_on_node(ctx, node_name, name_prefix)
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        print(
            f"ERROR: no pod named '{name_prefix}*' found on node {node_name!r} "
            f"in namespace {ctx.namespace!r}. Pass --pod to target one explicitly.",
            file=sys.stderr,
        )
    else:
        print(
            f"ERROR: multiple candidate pods on node {node_name!r}: {candidates}. "
            "Pass --pod to disambiguate.",
            file=sys.stderr,
        )
    sys.exit(1)
