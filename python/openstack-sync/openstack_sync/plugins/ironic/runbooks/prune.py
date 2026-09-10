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


def _spec_names(specs: list[dict[str, Any]]) -> set[str]:
    return {str(spec["runbookName"]) for spec in specs if spec.get("runbookName")}


def prune_removed_runbooks(
    conn: Any,
    desired_specs: list[dict[str, Any]],
    *,
    deleted_specs: list[dict[str, Any]],
    sweep_unseen: bool = True,
) -> None:
    """Delete operator-owned runbooks their CR no longer wants.

    *deleted_specs* names the runbooks whose CR just went away. *desired_specs*
    is what must survive, and is never deleted from.

    When *sweep_unseen* holds and there is a desired set to diff, this also
    deletes anything managed that the desired set does not name, catching a CR
    whose removal was never observed. The caller clears *sweep_unseen* when the
    desired set may be incomplete; an empty desired set is treated the same way,
    since it must never mean "delete every managed runbook".
    """
    desired_names = _spec_names(desired_specs)
    deleted_names = _spec_names(deleted_specs) - desired_names
    sweep = sweep_unseen and bool(desired_names)

    if not sweep and not deleted_names:
        LOG.warning(
            "Skipping Ironic runbook prune; nothing was deleted and there is no "
            "desired set to sweep against"
        )
        return

    LOG.info("Pruning removed Ironic runbooks")
    for runbook in client.list_runbooks(conn):
        name = get_value(runbook, "name")
        if not name or name in desired_names:
            continue
        if not sweep and name not in deleted_names:
            continue
        if not is_managed_runbook(runbook):
            LOG.info("Keeping Ironic runbook %s; it is not operator-owned", name)
            continue
        LOG.info("Deleting removed Ironic runbook %s", name)
        try:
            client.delete_runbook(conn, client.assigned_uuid(runbook, str(name)))
        except openstack_exceptions.ConflictException:
            LOG.info("Ironic runbook %s is still in use; skipping delete", name)
