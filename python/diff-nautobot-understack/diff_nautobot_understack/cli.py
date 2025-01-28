import typer
from diff_nautobot_understack.project.main import (
    openstack_project_diff_from_nautobot_tenant,
)
from diff_nautobot_understack.network.main import (
    openstack_network_diff_from_ucvni_network,
)
from diff_nautobot_understack.settings import app_settings as settings

app = typer.Typer(
    name="diff",
    add_completion=False,
    help="compare data between Openstack and Nautobot.",
)


@app.command()
def project(
    name: str,
    debug: bool = typer.Option(False, "--debug", "-v", help="Enable debug mode"),
):
    """Nautobot tenants ⟹ Openstack projects"""
    settings.debug = debug
    openstack_project_diff_from_nautobot_tenant(os_project=name)


@app.command()
def network(
    debug: bool = typer.Option(False, "--debug", "-v", help="Enable debug mode"),
):
    """Nautobot ucvnis ⟹ Openstack networks"""
    settings.debug = debug
    openstack_network_diff_from_ucvni_network()


if __name__ == "__main__":
    app()
