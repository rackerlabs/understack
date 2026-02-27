"""Shared utilities for resync operations.

Common patterns for resyncing data from various sources to Nautobot.
"""

import argparse
import logging
from dataclasses import dataclass

import pynautobot

from understack_workflows.helpers import credential
from understack_workflows.helpers import parser_nautobot_args

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_SYNC_FAILURES = 1


@dataclass
class SyncResult:
    """Result of a sync operation."""

    total: int = 0
    failed: int = 0
    skipped: int = 0

    @property
    def succeeded(self) -> int:
        return self.total - self.failed - self.skipped


def parser_resync_args(
    parser: argparse.ArgumentParser,
    item_name: str = "item",
    item_flag: str = "--item",
) -> argparse.ArgumentParser:
    """Add common resync arguments to a parser.

    Args:
        parser: ArgumentParser to add arguments to
        item_name: Name of the item being synced (for help text)
        item_flag: Flag name for specifying a single item

    Returns:
        The parser with added arguments
    """
    parser.add_argument(
        item_flag,
        type=str,
        help=f"Sync specific {item_name} UUID (default: all {item_name}s)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=f"List {item_name}s without syncing",
    )
    return parser_nautobot_args(parser)


def get_nautobot_client(args: argparse.Namespace) -> pynautobot.api:
    """Create a Nautobot API client from parsed arguments."""
    nb_token = args.nautobot_token or credential("nb-token", "token")
    return pynautobot.api(args.nautobot_url, token=nb_token)


def log_sync_result(
    result: SyncResult,
    item_name: str,
    dry_run: bool = False,
) -> int:
    """Log sync results and return appropriate exit code.

    Args:
        result: SyncResult from the sync operation
        item_name: Name of the item type (e.g., "node", "project")
        dry_run: Whether this was a dry run

    Returns:
        Exit code (EXIT_SUCCESS or EXIT_SYNC_FAILURES)
    """
    if dry_run:
        count = result.total - result.skipped
        msg = f"Dry run complete. {count} {item_name}s would be synced"
        if result.skipped:
            msg += f" ({result.skipped} skipped)"
        logger.info("%s.", msg)
    else:
        msg = (
            f"Sync complete. {result.succeeded}/{result.total} "
            f"{item_name}s synced successfully"
        )
        if result.skipped:
            msg += f" ({result.skipped} skipped)"
        logger.info("%s.", msg)

    if result.failed:
        logger.error("Failed to sync %d %ss", result.failed, item_name)
        return EXIT_SYNC_FAILURES

    return EXIT_SUCCESS
