"""Raw passthrough commands: nbctl, sbctl, vsctl, appctl."""

from __future__ import annotations

from typing import Annotated

import typer

from us_net import kube
from us_net.connection import ConnectionContext
from us_net.connection import print_connection_banner
from us_net.ovn import OVSDB_CONTAINER

PASSTHROUGH_SETTINGS = {"ignore_unknown_options": True, "allow_extra_args": True}

# typer.Argument() would trip ruff's B008 (function call in a default) if used
# as the default value directly, so the catch-all args param is declared via
# Annotated instead -- keep the actual default (None) on the function param.
PassthroughArgs = Annotated[list[str] | None, typer.Argument()]


def nbctl(ctx: typer.Context, args: PassthroughArgs = None) -> None:
    """Run ovn-nbctl against the Northbound DB pod."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx)
    rc = kube.stream_exec_in_pod(
        conn_ctx, conn_ctx.nb_pod, OVSDB_CONTAINER, ["ovn-nbctl", *(args or [])]
    )
    raise typer.Exit(rc)


def sbctl(ctx: typer.Context, args: PassthroughArgs = None) -> None:
    """Run ovn-sbctl against the Southbound DB pod."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx)
    rc = kube.stream_exec_in_pod(
        conn_ctx, conn_ctx.sb_pod, OVSDB_CONTAINER, ["ovn-sbctl", *(args or [])]
    )
    raise typer.Exit(rc)


def vsctl(
    ctx: typer.Context,
    node: str = typer.Option(..., "--node", help="Node to run ovs-vsctl on"),
    pod: str = typer.Option(None, "--pod", help="Exact pod, bypassing node discovery"),
    container: str = typer.Option(
        None, "--container", help="Container to exec into (default: pod's default)"
    ),
    args: PassthroughArgs = None,
) -> None:
    """Run ovs-vsctl on --node's ovn-controller pod (OVS is co-located there)."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx)
    target_pod = kube.resolve_node_pod(conn_ctx, node, "ovn-controller", pod)
    rc = kube.stream_exec_in_pod(
        conn_ctx, target_pod, container, ["ovs-vsctl", *(args or [])]
    )
    raise typer.Exit(rc)


def appctl(
    ctx: typer.Context,
    node: str = typer.Option(..., "--node", help="Node to run ovs-appctl on"),
    target: str = typer.Option(
        "ovn-controller",
        "--target",
        help="Pod name-prefix to target; OVS is usually co-located with ovn-controller",
    ),
    pod: str = typer.Option(None, "--pod", help="Exact pod, bypassing node discovery"),
    container: str = typer.Option(
        None, "--container", help="Container to exec into (default: pod's default)"
    ),
    args: PassthroughArgs = None,
) -> None:
    """Run ovs-appctl against the ovn-controller pod on --node."""
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx)
    target_pod = kube.resolve_node_pod(conn_ctx, node, target, pod)
    rc = kube.stream_exec_in_pod(
        conn_ctx, target_pod, container, ["ovs-appctl", *(args or [])]
    )
    raise typer.Exit(rc)


def register(app: typer.Typer) -> None:
    """Attach nbctl/sbctl/vsctl/appctl directly onto the root app (no extra nesting)."""
    app.command("nbctl", context_settings=PASSTHROUGH_SETTINGS)(nbctl)
    app.command("sbctl", context_settings=PASSTHROUGH_SETTINGS)(sbctl)
    app.command("vsctl", context_settings=PASSTHROUGH_SETTINGS)(vsctl)
    app.command("appctl", context_settings=PASSTHROUGH_SETTINGS)(appctl)
