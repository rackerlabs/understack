"""kubectl-us-net: kubectl plugin for troubleshooting UnderStack's Neutron/OVN."""

from __future__ import annotations

import typer

from us_net.commands import raw
from us_net.commands import router
from us_net.connection import ConnectionContext

app = typer.Typer(
    name="kubectl-us-net",
    add_completion=False,
    no_args_is_help=True,
    help="Troubleshoot UnderStack's Neutron/OVN data plane.",
)


@app.callback()
def main(
    ctx: typer.Context,
    context: str = typer.Option(
        None, "--context", help="kubectl context to use (default: current-context)"
    ),
    namespace: str = typer.Option(
        "openstack", "--namespace", "-n", help="Namespace hosting the OVN NB/SB pods"
    ),
    nb_pod: str = typer.Option(
        "ovn-ovsdb-nb-0", "--nb-pod", help="Northbound OVSDB pod name"
    ),
    sb_pod: str = typer.Option(
        "ovn-ovsdb-sb-0", "--sb-pod", help="Southbound OVSDB pod name"
    ),
    os_cloud: str = typer.Option(
        None,
        "--os-cloud",
        help="OpenStack cloud name (default: OS_CLOUD env / clouds.yaml default)",
    ),
) -> None:
    """Set up the shared connection context used by every subcommand."""
    ctx.obj = ConnectionContext(
        kube_context=context,
        namespace=namespace,
        nb_pod=nb_pod,
        sb_pod=sb_pod,
        os_cloud=os_cloud,
    )


raw.register(app)
app.add_typer(router.app, name="router")


if __name__ == "__main__":
    app()
