"""Reconcile driver for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from typing import Protocol

from openstack_sync.hooks.framework.contracts import CleanupPolicy
from openstack_sync.hooks.framework.contracts import CredentialKey
from openstack_sync.hooks.framework.contracts import SyncPlan
from openstack_sync.hooks.framework.contracts import SyncPlugin
from openstack_sync.hooks.framework.contracts import SyncResource
from openstack_sync.hooks.framework.pruning import PruneResult
from openstack_sync.hooks.framework.resources import _resource_key
from openstack_sync.hooks.framework.resources import group_by_credentials
from openstack_sync.hooks.framework.status import synced_message
from openstack_sync.plugins.common import ConfigError

LOG = logging.getLogger(__name__)


class PatchStatus(Protocol):
    """Patch one CR's status.

    ``extra_status`` and ``reason`` default to None: a failed reconcile has
    nothing extra to report, and reports the generic failure reason.
    """

    def __call__(
        self,
        plugin: SyncPlugin,
        resource: SyncResource,
        sync_status: str,
        message: str,
        extra_status: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> None: ...


SyncLiveFinalizers = Callable[
    [SyncPlugin, list[SyncResource], CleanupPolicy],
    set[tuple[str | None, str | None]],
]
ReleaseDeletedFinalizers = Callable[[SyncPlugin, list[SyncResource]], int]
RunPrune = Callable[
    [SyncPlugin, SyncPlan, dict[CredentialKey, Any], CleanupPolicy], PruneResult
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
                result = plugin.reconcile(conn, resource.spec, cache)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                patch_status(
                    plugin, resource, "Failed", str(exc), reason=_failure_reason(exc)
                )
                LOG.error(
                    "Failed to reconcile %s %s: %s", noun, resource.display_name, exc
                )
                continue

            if result.notes:
                LOG.warning(
                    "%s %s converged but needs manual action: %s",
                    noun.capitalize(),
                    resource.display_name,
                    "; ".join(result.notes),
                )
            patch_status(
                plugin,
                resource,
                "Synced",
                synced_message(noun, result.notes),
                extra_status=result.extra_status,
            )

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
        if not cleanup_policy.uses_finalizer:
            release_deleted_finalizers(plugin, inputs.deleted_resources)
        return 1

    prune_result = run_prune(plugin, inputs, connections, cleanup_policy)

    # A finalizer is only held while destructive, CR-scoped cleanup could still
    # be outstanding, so it is released once that cleanup has run for the CR's
    # credential group. A failed finalized prune keeps finalizers only for the
    # deleted CRs that used the failed credentials; unrelated deleted CRs can
    # finish once their own credential group succeeded. When
    # cleanup_policy.uses_finalizer is false there is no finalizer-backed
    # cleanup to wait for: any finalizer on a deleted CR is stale under the
    # current policy, and it must be released even if a best-effort prune could
    # not connect.
    resources_to_release = inputs.deleted_resources
    if cleanup_policy.uses_finalizer:
        resources_to_release = [
            resource
            for resource in inputs.deleted_resources
            if resource.credentials not in prune_result.failed_credentials
        ]

    release_code = release_deleted_finalizers(plugin, resources_to_release)
    return prune_result.exit_code or release_code


def _fail_group(
    plugin: SyncPlugin,
    group: list[SyncResource],
    message: str,
    patch_status: PatchStatus,
) -> None:
    for resource in group:
        patch_status(plugin, resource, "Failed", message)


def _failure_reason(exc: Exception) -> str | None:
    """Return the reason a ConfigError names, or None for any other error."""
    if not isinstance(exc, ConfigError):
        return None
    reason = exc.reason
    return reason if isinstance(reason, str) and reason else None
