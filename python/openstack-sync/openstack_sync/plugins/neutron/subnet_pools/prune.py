"""Delete Neutron subnet pools whose CR was removed."""

from __future__ import annotations

import logging
from typing import Any

from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.neutron.subnet_pools.markers import is_managed_subnet_pool

LOG = logging.getLogger(__name__)


def prune_removed_subnet_pools(
    conn: Any,
    desired_names: list[str],
    *,
    authoritative_empty: bool = False,
) -> None:
    """Delete operator-owned subnet pools absent from the desired names.

    *desired_names* are the Neutron pool names the surviving CRs declare (see
    ``reconcile.resolve_desired_names``), read straight from ``spec.name`` with
    no Nautobot call, so prune stays independent of Nautobot reachability.
    """
    if not desired_names and not authoritative_empty:
        LOG.warning(
            "No desired subnet pools found; skipping prune to avoid deleting "
            "all managed subnet pools"
        )
        return

    wanted = {str(name) for name in desired_names if name}
    incomplete = []
    LOG.info("Pruning removed subnet pools")
    for pool in list(conn.network.subnet_pools()):
        name = get_value(pool, "name")
        if not name or name in wanted:
            continue
        if not is_managed_subnet_pool(pool):
            continue

        pool_id = resource_id(pool)
        LOG.info("Deleting removed subnet pool %s (%s)", name, pool_id)
        try:
            conn.network.delete_subnet_pool(pool, ignore_missing=True)
        except openstack_exceptions.NotFoundException:
            LOG.info("Subnet pool %s (%s) is already absent", name, pool_id)
        except openstack_exceptions.ConflictException:
            LOG.info("Subnet pool %s is still in use; skipping delete", name)
            incomplete.append(str(name))

    if incomplete:
        raise RuntimeError("subnet pools still present: " + ", ".join(incomplete))
