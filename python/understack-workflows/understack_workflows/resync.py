"""Shared utilities for resync operations."""

import argparse
import logging
from dataclasses import dataclass

import pynautobot

from understack_workflows.helpers import credential

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


def get_nautobot_client(args: argparse.Namespace) -> pynautobot.api:
    """Create a Nautobot API client from parsed arguments."""
    nb_token = args.nautobot_token or credential("nb-token", "token")
    return pynautobot.api(args.nautobot_url, token=nb_token)


def log_sync_result(result: SyncResult, item_name: str) -> int:
    """Log sync results and return appropriate exit code."""
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
