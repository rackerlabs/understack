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

from understack_workflows.helpers import parser_nautobot_args
from understack_workflows.helpers import setup_logger
from understack_workflows.main.sync_keystone import handle_project_update
from understack_workflows.main.sync_keystone import is_domain
from understack_workflows.openstack.client import Connection
from understack_workflows.openstack.client import get_openstack_client
from understack_workflows.resync import SyncResult
from understack_workflows.resync import get_nautobot_client
from understack_workflows.resync import log_sync_result

logger = logging.getLogger(__name__)


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resync Keystone projects to Nautobot tenants"
    )
    return parser_nautobot_args(parser)


def sync_projects(conn: Connection, nautobot: pynautobot.api) -> SyncResult:
    """Sync Keystone projects to Nautobot tenants."""
    result = SyncResult()
    projects = list(conn.identity.projects())  # pyright: ignore[reportAttributeAccessIssue]

    for project in projects:
        result.total += 1

        if is_domain(project):
            logger.debug("Skipping domain: %s (%s)", project.id, project.name)
            result.skipped += 1
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
    result = sync_projects(conn, nautobot)

    return log_sync_result(result, "project")
