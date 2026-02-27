"""Resync Ironic nodes to Nautobot.

Use when Nautobot gets out of sync with Ironic, e.g., after:
- Nautobot database restore
- Missed events
- Manual Nautobot changes
"""

import argparse
import logging

import pynautobot

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.oslo_event.nautobot_device_sync import sync_device_to_nautobot
from understack_workflows.resync import SyncResult
from understack_workflows.resync import get_nautobot_client
from understack_workflows.resync import log_sync_result
from understack_workflows.resync import parser_resync_args

logger = logging.getLogger(__name__)


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Resync Ironic nodes to Nautobot")
    return parser_resync_args(parser, item_name="node", item_flag="--node")


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

    nautobot = get_nautobot_client(args)
    result = sync_nodes(nautobot, args.node or None, args.dry_run)

    return log_sync_result(result, "node", args.dry_run)
