"""Resync Keystone projects to Nautobot tenants.

Use when Nautobot gets out of sync with Keystone, e.g., after:
- Nautobot database restore
- Missed events
- Manual Nautobot changes
"""

import argparse
import logging
import uuid

import pynautobot

from understack_workflows.helpers import setup_logger
from understack_workflows.main.sync_keystone import handle_project_update
from understack_workflows.main.sync_keystone import is_domain
from understack_workflows.openstack.client import Connection
from understack_workflows.openstack.client import get_openstack_client
from understack_workflows.resync import SyncResult
from understack_workflows.resync import get_nautobot_client
from understack_workflows.resync import log_sync_result
from understack_workflows.resync import parser_resync_args

logger = logging.getLogger(__name__)


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resync Keystone projects to Nautobot tenants"
    )
    return parser_resync_args(parser, item_name="project", item_flag="--project")


def sync_projects(
    conn: Connection,
    nautobot: pynautobot.api,
    project_uuid: str | None = None,
    dry_run: bool = False,
) -> SyncResult:
    """Sync Keystone projects to Nautobot tenants.

    Args:
        conn: OpenStack connection
        nautobot: Nautobot API instance
        project_uuid: Optional specific project UUID to sync (syncs all if None)
        dry_run: If True, only log what would be synced

    Returns:
        SyncResult with total, failed, and skipped counts
    """
    result = SyncResult()

    if project_uuid:
        projects = [conn.identity.get_project(project_uuid)]  # pyright: ignore[reportAttributeAccessIssue]
    else:
        projects = list(conn.identity.projects())  # pyright: ignore[reportAttributeAccessIssue]

    for project in projects:
        result.total += 1

        if is_domain(project):
            logger.debug("Skipping domain: %s (%s)", project.id, project.name)
            result.skipped += 1
            continue

        if dry_run:
            logger.info("Would sync project: %s (%s)", project.id, project.name)
            continue

        logger.info("Syncing project: %s (%s)", project.id, project.name)
        if handle_project_update(conn, nautobot, uuid.UUID(project.id)) != 0:
            result.failed += 1
            logger.error("Failed to sync project %s", project.id)

    return result


def main() -> int:
    setup_logger(level=logging.INFO)
    args = argument_parser().parse_args()

    conn = get_openstack_client()
    nautobot = get_nautobot_client(args)
    result = sync_projects(conn, nautobot, args.project or None, args.dry_run)

    return log_sync_result(result, "project", args.dry_run)
