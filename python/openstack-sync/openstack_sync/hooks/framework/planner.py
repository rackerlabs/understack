"""Binding-context planning for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import logging
from typing import Any

from openstack_sync.hooks.framework.common import snapshot_items
from openstack_sync.hooks.framework.common import synchronization_items
from openstack_sync.hooks.framework.contracts import HookConfig
from openstack_sync.hooks.framework.contracts import SyncPlan
from openstack_sync.hooks.framework.contracts import SyncResource
from openstack_sync.hooks.framework.resources import _credentials
from openstack_sync.hooks.framework.resources import _dedupe_resources
from openstack_sync.hooks.framework.resources import _ResourceReader
from openstack_sync.plugins.common import ConfigError

LOG = logging.getLogger(__name__)


def _status_is_current(resource: SyncResource) -> bool:
    """Return True when the CR status already records this generation as Synced.

    The hook's own status patch surfaces as a Modified event carrying the same
    ``metadata.generation``. Without this check the hook would reconcile itself
    in a loop.
    """
    status = resource.current_status
    return (
        resource.generation is not None
        and status is not None
        and status.get("syncStatus") == "Synced"
        and status.get("observedGeneration") == resource.generation
    )


def _split_events(
    contexts: list[dict[str, Any]], config: HookConfig, reader: _ResourceReader
) -> tuple[list[SyncResource], list[SyncResource], bool]:
    """Split this binding's Event contexts into changed and deleted resources.

    Shell-operator can replay a backlog of events for one CR. Collapsing by CR
    identity keeps one logical resource from producing repeated finalizer,
    status, reconcile, and prune work in the same hook run.
    """
    changed: dict[str, SyncResource] = {}
    deleted: dict[str, SyncResource] = {}
    saw_event_context = False
    changed_events = 0
    changed_identities: set[str] = set()

    for context in contexts:
        if context.get("binding") != config.binding_name:
            continue
        if context.get("type") != "Event":
            continue
        saw_event_context = True

        watch_event = context.get("watchEvent")
        if not watch_event:
            LOG.warning("%s event carries no watchEvent; ignoring it", config.crd_kind)
            continue

        obj = context.get("object")
        if not obj:
            LOG.warning(
                "%s %s event carries no object; ignoring it",
                config.crd_kind,
                watch_event,
            )
            continue

        resource = reader.read(obj, f"{watch_event} CR")
        if resource is None:
            continue

        if resource.is_deleting or watch_event == "Deleted":
            deleted[resource.identity] = resource
            superseded = changed.pop(resource.identity, None)
            if superseded is not None:
                LOG.info(
                    "Not reconciling %s %s; a later event in this batch deleted it",
                    config.crd_kind,
                    superseded.display_name,
                )
        elif watch_event == "Modified" and _status_is_current(resource):
            LOG.info(
                "Skipping %s Modified event; generation %s is already Synced",
                resource.display_name,
                resource.generation,
            )
        else:
            deleted.pop(resource.identity, None)
            changed_events += 1
            changed_identities.add(resource.identity)
            changed[resource.identity] = resource

    if changed_events > len(changed_identities):
        LOG.info(
            "Collapsed %s %s changed event(s) across %s CR(s)",
            changed_events,
            config.crd_kind,
            len(changed_identities),
        )

    resources = sorted(changed.values(), key=lambda r: str(r.spec.get("name", "")))
    return resources, list(deleted.values()), saw_event_context


def hook_inputs(contexts: list[dict[str, Any]], config: HookConfig) -> SyncPlan:
    """Split a shell-operator binding context by reconciliation purpose.

    Event-driven runs reconcile only the changed CRs but prune against the full
    desired set from the accompanying snapshot. Schedule and Synchronization
    runs reconcile everything they are given.
    """
    reader = _ResourceReader()
    changed, deleted, saw_event_context = _split_events(contexts, config, reader)

    if saw_event_context:
        event_contexts = [
            context
            for context in contexts
            if context.get("binding") == config.binding_name
            and context.get("type") == "Event"
        ]
        items = snapshot_items(list(reversed(event_contexts)), config.binding_name)
        if items is None:
            raise ConfigError(
                f"Shell-operator {config.binding_name} event context does not "
                f"contain {config.binding_name} snapshot objects"
            )
        desired, snapshot_deleted = reader.read_all(items)
        deleted = _dedupe_resources(deleted + snapshot_deleted)
        prune_credentials = _credentials(changed) | _credentials(deleted)
        return SyncPlan(
            changed, desired, deleted, prune_credentials, frozenset(reader.unreadable)
        )

    items = snapshot_items(contexts, config.binding_name)
    if items is None:
        items = synchronization_items(contexts, config.binding_name)
    if items is None:
        raise ConfigError(
            f"Shell-operator binding context does not contain "
            f"{config.binding_name} event, snapshot, or synchronization objects"
        )

    resources, deleted = reader.read_all(items)
    return SyncPlan(
        resources,
        resources,
        deleted,
        _credentials(resources) | _credentials(deleted),
        frozenset(reader.unreadable),
    )
