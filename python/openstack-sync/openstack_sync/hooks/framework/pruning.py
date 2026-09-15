"""Prune execution for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openstack_sync.hooks.framework.contracts import CleanupPolicy
from openstack_sync.hooks.framework.contracts import CredentialKey
from openstack_sync.hooks.framework.contracts import PruneRequest
from openstack_sync.hooks.framework.contracts import SyncPlan
from openstack_sync.hooks.framework.contracts import SyncPlugin
from openstack_sync.hooks.framework.resources import group_by_credentials

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class PruneResult:
    """Outcome of credential-scoped prune attempts."""

    exit_code: int
    failed_credentials: frozenset[CredentialKey]


def run_prune(
    plugin: SyncPlugin,
    inputs: SyncPlan,
    connections: dict[CredentialKey, Any],
    *,
    cleanup_policy: CleanupPolicy,
    get_connection: Callable[[str, str], Any],
) -> PruneResult:
    """Run the plugin's prune step for credential groups that need cleanup."""
    noun = plugin.noun
    failed_credentials: set[CredentialKey] = set()
    if not cleanup_policy.run_prune:
        LOG.info("Finished reconciling %s(s)", noun)
        return PruneResult(0, frozenset())

    grouped_desired = group_by_credentials(inputs.desired_resources_for_prune)
    grouped_deleted = group_by_credentials(inputs.deleted_resources)

    # Every group's desired resources, because a resource is not private to the
    # credentials that manage it. A plugin prunes by its own ownership marker,
    # which records no credential, and what a connection lists depends on its
    # token: a system-scoped credential sees what a project-scoped one manages,
    # and every credential sees what is public. The union is what keeps each
    # group's prune to the resources no group asked for.
    all_desired_specs = [
        resource.spec for resource in inputs.desired_resources_for_prune
    ]

    for credentials in sorted(inputs.prune_credentials):
        secret_name, cloud_name = credentials
        desired = grouped_desired.get(credentials, [])
        # An empty desired set is only authoritative when we know a CR was
        # deleted; otherwise it may just be a snapshot we could not read, and
        # pruning against it would delete everything.
        authoritative_empty = credentials in grouped_deleted and not desired
        if not desired and not authoritative_empty:
            LOG.info(
                "Skipping %s prune for cloud=%r secret=%r; no desired resources",
                noun,
                cloud_name,
                secret_name,
            )
            continue

        conn = connections.get(credentials)
        if conn is None:
            try:
                conn = get_connection(secret_name, cloud_name)
                plugin.wait_for_api(conn)
            except Exception as exc:  # noqa: BLE001
                failed_credentials.add(credentials)
                LOG.error(
                    "Cannot reach OpenStack for %s prune cloud=%r secret=%r: %s",
                    noun,
                    cloud_name,
                    secret_name,
                    exc,
                )
                continue
        connections[credentials] = conn

        try:
            plugin.prune_resources(
                conn,
                PruneRequest(
                    credentials=credentials,
                    desired_specs=all_desired_specs,
                    authoritative_empty=authoritative_empty,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            failed_credentials.add(credentials)
            LOG.error(
                "Failed to prune %s cloud=%r secret=%r: %s",
                noun,
                cloud_name,
                secret_name,
                exc,
            )

    if failed_credentials:
        return PruneResult(1, frozenset(failed_credentials))

    LOG.info("Finished reconciling %s(s)", noun)
    return PruneResult(0, frozenset())
