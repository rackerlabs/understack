"""Resync Ironic nodes to Nautobot.

Use when Nautobot gets out of sync with Ironic, e.g., after:
- Nautobot database restore
- Missed events
- Manual Nautobot changes
"""

import argparse
import logging
from dataclasses import dataclass

import pynautobot

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.oslo_event.nautobot_device_sync import sync_device_to_nautobot

logger = logging.getLogger(__name__)

_EXIT_SUCCESS = 0
_EXIT_SYNC_FAILURES = 1


@dataclass
class SyncResult:
    """Result of a sync operation."""

    total: int = 0
    failed: int = 0

    @property
    def succeeded(self) -> int:
        return self.total - self.failed


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resync Ironic nodes to Nautobot")
    parser.add_argument(
        "--node", type=str, help="Sync specific node UUID (default: all nodes)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="List nodes without syncing"
    )
    parser = parser_nautobot_args(parser)
    return parser


def sync_nodes(
    nautobot: pynautobot.api,
    node_uuid: str | None = None,
    dry_run: bool = False,
) -> SyncResult:
    """Sync Ironic nodes to Nautobot.

    Args:
        nautobot: Nautobot API instance
        node_uuid: Optional specific node UUID to sync (syncs all if None)
        dry_run: If True, only log what would be synced

    Returns:
        SyncResult with total and failed counts
    """
    ironic = IronicClient()
    nodes = [ironic.get_node(node_uuid)] if node_uuid else ironic.list_nodes()
    result = SyncResult()

    for node in nodes:
        result.total += 1

        if dry_run:
            logger.info("Would sync node: %s (%s)", node.uuid, node.name)
            continue

        logger.info("Syncing node: %s (%s)", node.uuid, node.name)
        if sync_device_to_nautobot(node.uuid, nautobot) != 0:
            result.failed += 1
            logger.error("Failed to sync node %s", node.uuid)

    return result


def main() -> int:
    setup_logger(level=logging.INFO)
    args = argument_parser().parse_args()

    nb_token = args.nautobot_token or credential("nb-token", "token")
    nautobot = pynautobot.api(args.nautobot_url, token=nb_token)

    result = sync_nodes(nautobot, args.node or None, args.dry_run)

    if args.dry_run:
        logger.info("Dry run complete. %d nodes would be synced.", result.total)
    else:
        logger.info(
            "Sync complete. %d/%d nodes synced successfully.",
            result.succeeded,
            result.total,
        )

    if result.failed:
        logger.error("Failed to sync %d nodes", result.failed)
        return _EXIT_SYNC_FAILURES

    return _EXIT_SUCCESS
