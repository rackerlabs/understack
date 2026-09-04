"""Ownership markers for operator-managed Ironic runbooks.

An IronicRunbook CR is an ownership claim for the Ironic runbook of the same
name. Runbooks the operator creates or adopts carry these markers in ``extra``,
Ironic's arbitrary metadata field; prune only deletes runbooks that have already
entered that managed set.
"""

from __future__ import annotations

from typing import Any

from openstack_sync.plugins.common import get_value

MANAGED_EXTRA_KEY = "_understack_runbook_operator"
MANAGED_EXTRA_VALUE = "managed"
MARKER_VERSION_EXTRA_KEY = "_understack_runbook_marker_version"
MARKER_VERSION_EXTRA_VALUE = "v1"
MARKER_SOURCE_EXTRA_KEY = "_understack_runbook_source"
MARKER_SOURCE_EXTRA_VALUE = "IronicRunbook"

#: Marker keys stamped into a managed runbook's ``extra``.
OPERATOR_EXTRA_MARKERS = {
    MANAGED_EXTRA_KEY: MANAGED_EXTRA_VALUE,
    MARKER_VERSION_EXTRA_KEY: MARKER_VERSION_EXTRA_VALUE,
    MARKER_SOURCE_EXTRA_KEY: MARKER_SOURCE_EXTRA_VALUE,
}


def runbook_extra(runbook: Any) -> dict[str, Any]:
    """Return the ``extra`` of *runbook* as a dict.

    Ironic models ``extra`` as nullable, so a runbook without one comes back as
    ``None``; an empty dict is the safe reading of that.
    """
    extra = get_value(runbook, "extra", default={})
    return extra if isinstance(extra, dict) else {}


def managed_extra(value: Any) -> dict[str, Any]:
    """Return *value* with the operator ownership markers merged in."""
    extra = value if isinstance(value, dict) else {}
    return {**extra, **OPERATOR_EXTRA_MARKERS}


def is_managed_runbook(runbook: Any) -> bool:
    """Return True when *runbook* carries the operator ownership marker."""
    return runbook_extra(runbook).get(MANAGED_EXTRA_KEY) == MANAGED_EXTRA_VALUE
