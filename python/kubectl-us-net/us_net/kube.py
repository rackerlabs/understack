"""kubectl exec/get wrappers used by the raw passthrough and higher-level commands."""

from __future__ import annotations

import json
import subprocess
import sys

from us_net.connection import ConnectionContext


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
