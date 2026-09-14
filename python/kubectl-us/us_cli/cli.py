"""kubectl-us: kubectl plugin for operating and troubleshooting UnderStack."""

from __future__ import annotations

import typer

from us_cli.commands import backup
from us_cli.commands import raw
from us_cli.commands import router
from us_cli.connection import ConnectionContext

app = typer.Typer(
    name="kubectl-us",
    add_completion=False,
    no_args_is_help=True,
    help="Operate and troubleshoot UnderStack.",
)

# `net` groups the Neutron/OVN data-plane troubleshooting commands
# (nbctl/sbctl/vsctl/appctl/router) so they live under `kubectl us net ...`,
# leaving room for other top-level groups like `backup`.
net_app = typer.Typer(
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


raw.register(net_app)
net_app.add_typer(router.app, name="router")

app.add_typer(net_app, name="net")
backup.register(app)


if __name__ == "__main__":
    app()
