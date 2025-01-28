import os
import sys

import typer
from diffsync.diff import Diff
from rich import print
from rich.console import Console
from rich.table import Table

from diff_nautobot_understack.network.main import (
    openstack_network_diff_from_ucvni_network,
)
from diff_nautobot_understack.project.main import (
    openstack_project_diff_from_nautobot_tenant,
)
from diff_nautobot_understack.settings import app_settings as settings

required_env_vars = ["NAUTOBOT_TOKEN", "NAUTOBOT_URL", "OS_CLOUD"]


app = typer.Typer(
    name="diff",
    add_completion=False,
    help="compare data between Openstack and Nautobot.",
)
diff_outputs = {
    "project": {"title": "Project Diff", "id_column_name": "Project ID"},
    "network": {"title": "Network Diff", "id_column_name": "Network ID"},
}


def display_output(
    diff_result: Diff, diff_output: str, output_format: str | None = None
):
    print(diff_result.summary())
    __output_format = (
        output_format if output_format is not None else settings.output_format
    )
    if __output_format == "table":
        diff_output_props = diff_outputs.get(diff_output)
        tabular_output(
            diff_result.dict().get(diff_output, {}),
            diff_output_props.get("title"),
            diff_output_props.get("id_column_name"),
        )
    else:
        print(diff_result.dict())


def tabular_output(diffs, title, id_column_name):
    table = Table(title=title, show_lines=True)

    table.add_column(id_column_name, style="cyan", no_wrap=True)
    table.add_column("Change Type", style="magenta")
    table.add_column("Details", style="yellow")

    for diff_id, changes in diffs.items():
        for change_type, details in changes.items():
            table.add_row(diff_id, change_type, str(details))

    console = Console()
    console.print(table)


@app.command()
def project(
    name: str,
    debug: bool = typer.Option(False, "--debug", "-v", help="Enable debug mode"),
    output_format: str = typer.Option(
        "json", "--format", help="Available formats json, table"
    ),
):
    """Nautobot tenants ⟹ Openstack projects"""
    settings.debug = debug
    diff_result = openstack_project_diff_from_nautobot_tenant(os_project=name)
    display_output(diff_result, "project", output_format)


@app.command()
def network(
    debug: bool = typer.Option(False, "--debug", "-v", help="Enable debug mode"),
    output_format: str = typer.Option(
        "json", "--format", help="Available formats json, table"
    ),
):
    """Nautobot ucvnis ⟹ Openstack networks"""
    settings.debug = debug
    diff_result = openstack_network_diff_from_ucvni_network()
    display_output(diff_result, "network", output_format)


def check_env_vars(required_vars):
    missing_vars = [var for var in required_vars if var not in os.environ]

    if missing_vars:
        print(f"Error: Missing environment variables: {', '.join(missing_vars)}")
        sys.exit(1)
    else:
        print("All required environment variables are set.")


check_env_vars(required_env_vars)
