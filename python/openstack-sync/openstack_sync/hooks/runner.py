"""Reconcile driver for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from openstack_sync.hooks.contracts import CleanupPolicy
from openstack_sync.hooks.contracts import CredentialKey
from openstack_sync.hooks.contracts import SyncPlan
from openstack_sync.hooks.contracts import SyncPlugin
from openstack_sync.hooks.contracts import SyncResource
from openstack_sync.hooks.resources import _resource_key
from openstack_sync.hooks.resources import group_by_credentials
from openstack_sync.hooks.status import synced_message

LOG = logging.getLogger("openstack_sync.hooks.framework")

PatchStatus = Callable[[SyncPlugin, SyncResource, str, str], None]
SyncLiveFinalizers = Callable[
    [SyncPlugin, list[SyncResource], CleanupPolicy],
    set[tuple[str | None, str | None]],
]
ReleaseDeletedFinalizers = Callable[[SyncPlugin, list[SyncResource]], int]
RunPrune = Callable[
    [SyncPlugin, SyncPlan, dict[CredentialKey, Any], CleanupPolicy], int
]


def run_sync(
    plugin: SyncPlugin,
    inputs: SyncPlan,
    *,
    get_connection: Callable[[str, str], Any],
    patch_status: PatchStatus,
    sync_live_finalizers: SyncLiveFinalizers,
    run_prune: RunPrune,
    release_deleted_finalizers: ReleaseDeletedFinalizers,
) -> int:
    """Reconcile every CR, then prune. Returns a process exit code."""
    noun = plugin.noun
    resources = inputs.resources_to_reconcile
    cleanup_policy = plugin.cleanup_policy()
    LOG.info("Found %s %s(s) to reconcile", len(resources), noun)

    connections: dict[CredentialKey, Any] = {}
    failed = 0

    unreadable = len(inputs.unreadable_resources)
    if unreadable:
        LOG.error(
            "Ignored %s unreadable %s(s): %s",
            unreadable,
            noun,
            ", ".join(sorted(inputs.unreadable_resources)),
        )

    finalizer_failures = sync_live_finalizers(plugin, resources, cleanup_policy)
    if finalizer_failures:
        failed += len(finalizer_failures)
        resources = [
            resource
            for resource in resources
            if _resource_key(resource) not in finalizer_failures
        ]

    grouped = group_by_credentials(resources)

    for credentials in sorted(grouped):
        secret_name, cloud_name = credentials
        group = grouped[credentials]

        try:
            conn = get_connection(secret_name, cloud_name)
        except Exception as exc:  # noqa: BLE001
            failed += len(group)
            _fail_group(
                plugin, group, f"OpenStack connection failed: {exc}", patch_status
            )
            LOG.error(
                "Failed to connect to OpenStack cloud=%r secret=%r: %s",
                cloud_name,
                secret_name,
                exc,
            )
            continue

        connections[credentials] = conn
        try:
            plugin.wait_for_api(conn)
        except Exception as exc:  # noqa: BLE001
            failed += len(group)
            _fail_group(
                plugin, group, f"OpenStack API unavailable: {exc}", patch_status
            )
            LOG.error(
                "OpenStack API unavailable for cloud=%r secret=%r: %s",
                cloud_name,
                secret_name,
                exc,
            )
            continue

        # Shared across every CR in this credential group so lookups made for
        # one CR are reused by the next.
        cache = plugin.new_cache()

        for resource in group:
            try:
                notes = plugin.reconcile(conn, resource.spec, cache)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                patch_status(plugin, resource, "Failed", str(exc))
                LOG.error(
                    "Failed to reconcile %s %s: %s", noun, resource.display_name, exc
                )
                continue

            if notes:
                LOG.warning(
                    "%s %s converged but needs manual action: %s",
                    noun.capitalize(),
                    resource.display_name,
                    "; ".join(notes),
                )
            patch_status(plugin, resource, "Synced", synced_message(noun, notes))

    if failed or unreadable:
        # Pruning deletes resources absent from the desired set. A CR that
        # failed to reconcile or could not be read at all means the desired set
        # could not be established, so deleting anything now risks removing a
        # resource that should exist.
        LOG.error(
            "Skipping %s prune; %s failed to reconcile and %s could not be read",
            noun,
            failed,
            unreadable,
        )
        return 1

    prune_code = run_prune(plugin, inputs, connections, cleanup_policy)

    # A finalizer is only held while destructive, CR-scoped cleanup could still
    # be outstanding, so it is released once that cleanup has run. When
    # cleanup_policy.uses_finalizer is false there is no such cleanup to wait
    # for: any finalizer still on a deleted CR is stale (left from when the
    # plugin did use one), and it must be released even if a best-effort prune
    # could not connect -- otherwise the CR is wedged in Terminating for a step
    # it does not depend on. When cleanup_policy.uses_finalizer is true a failed
    # prune keeps the finalizer, because the cleanup it guards did not complete.
    if cleanup_policy.uses_finalizer and prune_code != 0:
        return prune_code

    release_code = release_deleted_finalizers(plugin, inputs.deleted_resources)
    return prune_code or release_code


def _fail_group(
    plugin: SyncPlugin,
    group: list[SyncResource],
    message: str,
    patch_status: PatchStatus,
) -> None:
    for resource in group:
        patch_status(plugin, resource, "Failed", message)
