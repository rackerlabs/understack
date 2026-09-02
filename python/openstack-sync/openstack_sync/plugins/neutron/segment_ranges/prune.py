"""Delete network segment ranges whose CR was removed.

Everything here is gated on the operator's name-prefix ownership marker. A
range created out-of-band carries a plain name and is never in the managed set,
so it is untouched; a range carrying the owner prefix but absent from the
desired set is deleted.
"""

from __future__ import annotations

import logging
from typing import Any

from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.common import resource_id
from openstack_sync.plugins.neutron.segment_ranges.markers import is_managed_range
from openstack_sync.plugins.neutron.segment_ranges.markers import logical_name
from openstack_sync.plugins.neutron.segment_ranges.markers import managed_name

LOG = logging.getLogger(__name__)


def _delete_range(conn: Any, segment_range: Any) -> None:
    range_id = resource_id(segment_range)
    name = logical_name(str(get_value(segment_range, "name", default=range_id)))
    LOG.info("Deleting removed segment range %s (%s)", name, range_id)
    try:
        conn.network.delete_network_segment_range(
            segment_range, ignore_missing=True
        )
    except openstack_exceptions.NotFoundException:
        LOG.info("Segment range %s (%s) is already absent", name, range_id)
    except openstack_exceptions.ConflictException:
        LOG.info(
            "Segment range %s is still in use; skipping delete", name
        )


def prune_removed_ranges(
    conn: Any,
    desired_specs: list[dict[str, Any]],
    *,
    authoritative_empty: bool = False,
) -> None:
    """Delete operator-owned segment ranges absent from *desired_specs*.

    An empty *desired_specs* is only acted on when *authoritative_empty* says a
    CR really was deleted; otherwise it may be a snapshot we could not read, and
    pruning against it would delete every managed range.
    """
    if not desired_specs and not authoritative_empty:
        LOG.warning(
            "No desired segment ranges found; skipping prune to avoid deleting "
            "all managed ranges"
        )
        return

    desired_names = {
        managed_name(str(spec["name"])) for spec in desired_specs if spec.get("name")
    }

    LOG.info("Pruning removed segment ranges")
    for segment_range in list(conn.network.network_segment_ranges()):
        if not is_managed_range(segment_range):
            continue
        name = str(get_value(segment_range, "name", default=""))
        if name in desired_names:
            continue
        _delete_range(conn, segment_range)
