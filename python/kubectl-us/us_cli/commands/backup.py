"""`backup local`: download MariaDB + OVN NB/SB backups to the local machine.

Wraps the manual runbook steps (see
docs/environments/rxdb-upgrades.md and
docs/operator-guide/mariadb-upgrade-runbook.md) into one command so an
operator can grab a consistent set of local backups before an upgrade
without hand-copying pod names, container names, and socket paths.

Each backup is written to the current directory as
`<what>_backup_<context>_<epoch>.<ext>`, matching the filename convention
the OVN runbook already uses (e.g. `ovnnb_backup_rax-prod-iad3-rxdb-mt_<ts>.db`).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from us_cli import kube
from us_cli.connection import ConnectionContext
from us_cli.connection import print_connection_banner
from us_cli.connection import resolve_kube_context
from us_cli.ovn import OVSDB_CONTAINER

app = typer.Typer(
    no_args_is_help=True,
    help="Download UnderStack backups (MariaDB, OVN NB/SB) locally.",
)

# MariaDB logical-backup knobs, matching the mariadb-upgrade runbook's
# `mariadb-dump --single-transaction --routines --triggers --all-databases`.
MARIADB_POD = "mariadb-0"
MARIADB_CONTAINER = "mariadb"
MARIADB_DUMP_FLAGS = "--single-transaction --routines --triggers --all-databases"
# Run inside the pod via `sh -c` so $MARIADB_ROOT_PASSWORD (injected into the
# mariadb container by the mariadb-operator) expands remotely -- the secret
# value never reaches this process's argv, the kubectl argv, or the exec
# request; only the env-var *name* travels.
MARIADB_DUMP_SHELL = (
    f'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb-dump -u root {MARIADB_DUMP_FLAGS}'
)

# ovsdb-client reads each DB over its local unix socket inside the ovsdb
# container of the NB/SB pods -- these are the socket paths the runbook uses.
OVN_NB_SOCKET = "unix:/var/run/ovn/ovnnb_db.sock"
OVN_SB_SOCKET = "unix:/var/run/ovn/ovnsb_db.sock"


@dataclass
class BackupResult:
    label: str
    path: Path


def _slug(value: str) -> str:
    """Filesystem-safe slug for the context, e.g. rax_prod_iad3 -> rax-prod-iad3."""
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return slug or "unknown"


def _dest(directory: Path, what: str, context_slug: str, ext: str, ts: int) -> Path:
    return directory / f"{what}_backup_{context_slug}_{ts}.{ext}"


def _backup_ovn(
    conn_ctx: ConnectionContext,
    pod: str,
    socket: str,
    what: str,
    directory: Path,
    context_slug: str,
    ts: int,
) -> BackupResult:
    dest = _dest(directory, what, context_slug, "db", ts)
    kube.exec_to_file(
        conn_ctx,
        pod,
        OVSDB_CONTAINER,
        ["ovsdb-client", "backup", socket],
        str(dest),
    )
    return BackupResult(label=what, path=dest)


def _backup_mariadb(
    conn_ctx: ConnectionContext,
    directory: Path,
    context_slug: str,
    ts: int,
) -> BackupResult:
    dest = _dest(directory, "mariadb", context_slug, "sql", ts)
    argv = ["sh", "-c", MARIADB_DUMP_SHELL]
    kube.exec_to_file(conn_ctx, MARIADB_POD, MARIADB_CONTAINER, argv, str(dest))
    return BackupResult(label="mariadb", path=dest)


# typer.Option(Path(".")) would trip ruff's B008 (a function call -- Path(".")
# -- in a default), so the directory option is declared via Annotated with a
# plain default of None, resolved to the current dir inside the command.
DirectoryOpt = Annotated[
    Path | None,
    typer.Option(
        "--directory",
        "-d",
        help="Local directory to write backup files into (default: current dir)",
    ),
]


@app.command("local")
def local(
    ctx: typer.Context,
    directory: DirectoryOpt = None,
    skip_mariadb: bool = typer.Option(
        False, "--skip-mariadb", help="Skip the MariaDB logical backup"
    ),
    skip_ovn: bool = typer.Option(
        False, "--skip-ovn", help="Skip the OVN NB/SB database backups"
    ),
) -> None:
    """Download MariaDB, OVN NB, and OVN SB backups to the local machine.

    Produces (in --directory, default the current dir):
      - mariadb_backup_<context>_<epoch>.sql  (mariadb-dump --all-databases)
      - ovnnb_backup_<context>_<epoch>.db     (ovsdb-client backup, NB)
      - ovnsb_backup_<context>_<epoch>.db     (ovsdb-client backup, SB)
    """
    conn_ctx: ConnectionContext = ctx.obj
    print_connection_banner(conn_ctx)

    directory = directory or Path(".")

    if skip_mariadb and skip_ovn:
        typer.echo(
            "ERROR: --skip-mariadb and --skip-ovn together leave nothing to back up.",
            err=True,
        )
        raise typer.Exit(2)

    directory.mkdir(parents=True, exist_ok=True)
    context_slug = _slug(resolve_kube_context(conn_ctx.kube_context))
    # One shared timestamp so a run's files sort together as a set.
    ts = int(time.time())

    results: list[BackupResult] = []
    try:
        if not skip_mariadb:
            typer.echo("Backing up MariaDB (all databases) ...")
            results.append(_backup_mariadb(conn_ctx, directory, context_slug, ts))
        if not skip_ovn:
            typer.echo("Backing up OVN Northbound DB ...")
            results.append(
                _backup_ovn(
                    conn_ctx,
                    conn_ctx.nb_pod,
                    OVN_NB_SOCKET,
                    "ovnnb",
                    directory,
                    context_slug,
                    ts,
                )
            )
            typer.echo("Backing up OVN Southbound DB ...")
            results.append(
                _backup_ovn(
                    conn_ctx,
                    conn_ctx.sb_pod,
                    OVN_SB_SOCKET,
                    "ovnsb",
                    directory,
                    context_slug,
                    ts,
                )
            )
    except kube.BackupExecError as exc:
        typer.echo(f"\nERROR: {exc}", err=True)
        raise typer.Exit(1) from exc

    print("\nBackups written:")
    for result in results:
        size = result.path.stat().st_size if result.path.exists() else 0
        print(f"  {result.label:<8} -> {result.path} ({size} bytes)")


def register(app_root: typer.Typer) -> None:
    """Attach the `backup` command group onto the root app."""
    app_root.add_typer(app, name="backup")
