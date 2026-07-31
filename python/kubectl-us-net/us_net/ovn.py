"""ovn-nbctl / ovn-sbctl helpers: exec wrappers + OVSDB JSON unwrapping.

The unwrap logic is ported from scripts/cleanup_dead_ovn_ha_chassis.py, which
already solved the problem of turning `--format=json` OVSDB output into plain
Python values.
"""

from __future__ import annotations

import json
import sys

from us_net import kube
from us_net.connection import ConnectionContext

OVSDB_CONTAINER = "ovsdb"


def _unwrap_ovn_value(val):
    """Recursively unwrap an OVN JSON-encoded value."""
    if not isinstance(val, list) or len(val) < 2:
        return val
    tag = val[0]
    if tag == "uuid":
        return val[1]
    if tag == "set":
        return [_unwrap_ovn_value(v) for v in val[1]]
    if tag == "map":
        return {_unwrap_ovn_value(k): _unwrap_ovn_value(v) for k, v in val[1]}
    return val


def parse_ovn_json(raw: str) -> list[dict]:
    """Parse OVN --format=json list/find output into a list of row dicts."""
    obj = json.loads(raw)
    headings = obj["headings"]
    return [
        {h: _unwrap_ovn_value(v) for h, v in zip(headings, row, strict=True)}
        for row in obj["data"]
    ]


def as_list(val) -> list:
    """OVSDB unwraps single-element sets to a bare value instead of a list."""
    if val in (None, ""):
        return []
    return val if isinstance(val, list) else [val]


def _run(ctx: ConnectionContext, pod: str, ctl: str, args: list[str]) -> str:
    result = kube.exec_in_pod(ctx, pod, OVSDB_CONTAINER, [ctl, *args])
    if result.returncode != 0:
        print(
            f"ERROR: {ctl} {' '.join(args)} failed:\n{result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)
    return result.stdout


def nbctl_raw(ctx: ConnectionContext, args: list[str]) -> str:
    """Run ovn-nbctl against the Northbound pod, returning raw stdout."""
    return _run(ctx, ctx.nb_pod, "ovn-nbctl", args)


def sbctl_raw(ctx: ConnectionContext, args: list[str]) -> str:
    """Run ovn-sbctl against the Southbound pod, returning raw stdout."""
    return _run(ctx, ctx.sb_pod, "ovn-sbctl", args)


def nbctl_list(ctx: ConnectionContext, table: str) -> list[dict]:
    """`ovn-nbctl list <table>` as parsed JSON rows."""
    return parse_ovn_json(nbctl_raw(ctx, ["--format=json", "list", table]))


def sbctl_list(ctx: ConnectionContext, table: str) -> list[dict]:
    """`ovn-sbctl list <table>` as parsed JSON rows."""
    return parse_ovn_json(sbctl_raw(ctx, ["--format=json", "list", table]))


def nbctl_find(ctx: ConnectionContext, table: str, condition: str) -> list[dict]:
    """`ovn-nbctl find <table> <condition>` as parsed JSON rows."""
    return parse_ovn_json(nbctl_raw(ctx, ["--format=json", "find", table, condition]))


def sbctl_lflow_list(ctx: ConnectionContext, datapath_name: str) -> str:
    """`ovn-sbctl lflow-list <datapath_name>` raw table output."""
    return sbctl_raw(ctx, ["lflow-list", datapath_name])
