"""Finalizer orchestration helpers for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

from openstack_sync.hooks.common import CustomResourceTarget
from openstack_sync.hooks.contracts import FINALIZER
from openstack_sync.hooks.contracts import CleanupPolicy
from openstack_sync.hooks.contracts import HookConfig
from openstack_sync.hooks.contracts import SyncResource
from openstack_sync.hooks.resources import _resource_key

LOG = logging.getLogger("openstack_sync.hooks.framework")


class _FinalizerPlugin(Protocol):
    config: HookConfig


def resource_target(
    config: HookConfig, resource: SyncResource
) -> CustomResourceTarget | None:
    """Return the Kubernetes patch target for *resource*, or None if unusable."""
    if not resource.name:
        LOG.error(
            "Unable to patch finalizers on %s; Kubernetes metadata.name is missing",
            config.crd_kind,
        )
        return None
    return CustomResourceTarget(
        name=resource.name,
        namespace=resource.namespace or config.namespace,
        api_version=config.crd_api_version,
        resource=config.crd_resource,
        kind=config.crd_kind,
    )


def write_finalizer(
    config: HookConfig,
    resource: SyncResource,
    *,
    present: bool,
    add_finalizer: Callable[..., bool],
    remove_finalizer: Callable[..., bool],
) -> bool:
    """Add or remove the framework finalizer on a live CR.

    ``present`` says which state the CR should end in. This helper is for live
    CRs; deleted CRs use ``release_deleted_finalizers`` so an already-gone
    object can be treated as success.
    """
    target = resource_target(config, resource)
    if target is None:
        return False
    if present:
        return add_finalizer(
            target=target,
            finalizer=FINALIZER,
            current_finalizers=list(resource.finalizers),
            resource_version=resource.resource_version,
        )
    return remove_finalizer(
        target=target,
        finalizer=FINALIZER,
        current_finalizers=list(resource.finalizers),
    )


def sync_live_finalizers(
    plugin: _FinalizerPlugin,
    resources: list[SyncResource],
    *,
    cleanup_policy: CleanupPolicy,
    add_finalizer: Callable[..., bool],
    remove_finalizer: Callable[..., bool],
    fail_resource: Callable[[SyncResource, str], None],
) -> set[tuple[str | None, str | None]]:
    """Make live CR finalizers match the plugin's current cleanup policy."""
    should_have_finalizer = cleanup_policy.uses_finalizer
    failed: set[tuple[str | None, str | None]] = set()
    for resource in resources:
        if resource.has_finalizer == should_have_finalizer:
            continue
        if write_finalizer(
            plugin.config,
            resource,
            present=should_have_finalizer,
            add_finalizer=add_finalizer,
            remove_finalizer=remove_finalizer,
        ):
            continue

        failed.add(_resource_key(resource))
        message = (
            "Unable to add finalizer before reconciling"
            if should_have_finalizer
            else "Unable to remove disabled finalizer before reconciling"
        )
        fail_resource(resource, message)
    return failed


def release_deleted_finalizers(
    config: HookConfig,
    resources: list[SyncResource],
    *,
    release_finalizer: Callable[..., bool],
) -> int:
    """Remove finalizers from deleted CRs after cleanup has succeeded."""
    failed = 0
    for resource in resources:
        if not resource.has_finalizer:
            continue
        target = resource_target(config, resource)
        if target is None or not release_finalizer(
            target=target,
            finalizer=FINALIZER,
            current_finalizers=list(resource.finalizers),
        ):
            failed += 1
    return 1 if failed else 0
