"""Delete Ironic runbooks whose CR was removed.

Everything here is gated on the operator's ownership marker. A hand-made runbook
is untouched until a CR causes the operator to create or adopt it; a runbook
carrying the marker is in the operator-managed set, which makes any further
filtering redundant.

There is no in-use check to make: a runbook is named in a clean or service
request as that request is made, and Ironic keeps no reference from a node back
to a runbook.
"""

from __future__ import annotations

import logging
from typing import Any

from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.ironic.runbooks import client
from openstack_sync.plugins.ironic.runbooks.markers import is_managed_runbook

LOG = logging.getLogger(__name__)


def _delete_runbook(conn: Any, name: str) -> None:
    LOG.info("Deleting removed Ironic runbook %s", name)
    try:
        client.delete_runbook(conn, name)
    except openstack_exceptions.ConflictException:
        LOG.info("Ironic runbook %s is still in use; skipping delete", name)


def prune_removed_runbooks(
    conn: Any,
    desired_specs: list[dict[str, Any]],
    *,
    authoritative_empty: bool = False,
) -> None:
    """Delete operator-owned runbooks absent from *desired_specs*.

    An empty *desired_specs* is only acted on when *authoritative_empty* says a
    CR really was deleted; otherwise it may be a snapshot we could not read, and
    pruning against it would delete every managed runbook.
    """
    if not desired_specs and not authoritative_empty:
        LOG.warning(
            "No desired Ironic runbooks found; skipping prune to avoid deleting "
            "all managed runbooks"
        )
        return

    desired_names = {
        str(spec["runbookName"]) for spec in desired_specs if spec.get("runbookName")
    }

    LOG.info("Pruning removed Ironic runbooks")
    for runbook in client.list_runbooks(conn):
        name = get_value(runbook, "name")
        if not name or name in desired_names:
            continue
        if not is_managed_runbook(runbook):
            LOG.info("Keeping Ironic runbook %s; it is not operator-owned", name)
            continue
        _delete_runbook(conn, str(name))
