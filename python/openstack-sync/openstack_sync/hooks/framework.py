"""Framework for CR-driven OpenStack resource sync plugins.

A plugin supplies four things: how to wait for its OpenStack service, how to
converge one CR spec, an optional per-credential-group cache, and an optional
prune. This module supplies everything else -- shell-operator hook config,
credential grouping, connection setup, per-resource status patching, the
reconcile-then-prune ordering, and the exit code contract.

See ``README.md`` for the steps to add a plugin.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any

from openstack_sync.hooks.common import CustomResourceTarget
from openstack_sync.hooks.common import add_resource_finalizer
from openstack_sync.hooks.common import configure_logging
from openstack_sync.hooks.common import patch_resource_status
from openstack_sync.hooks.common import read_binding_context
from openstack_sync.hooks.common import release_deleted_resource_finalizer
from openstack_sync.hooks.common import remove_resource_finalizer
from openstack_sync.hooks.config import build_crd_hook_config
from openstack_sync.hooks.config import hook_enabled
from openstack_sync.hooks.contracts import FINALIZER
from openstack_sync.hooks.contracts import CredentialKey
from openstack_sync.hooks.contracts import HookConfig
from openstack_sync.hooks.contracts import HookInputs
from openstack_sync.hooks.contracts import SyncPlugin
from openstack_sync.hooks.contracts import SyncResource
from openstack_sync.hooks.entrypoint import run_hook as _run_hook
from openstack_sync.hooks.finalizers import release_deleted_finalizers
from openstack_sync.hooks.finalizers import resource_target
from openstack_sync.hooks.finalizers import sync_live_finalizers
from openstack_sync.hooks.finalizers import write_finalizer
from openstack_sync.hooks.planner import hook_inputs
from openstack_sync.hooks.pruning import run_prune
from openstack_sync.hooks.resources import _resource_key
from openstack_sync.hooks.resources import group_by_credentials
from openstack_sync.hooks.status import patch_status
from openstack_sync.hooks.status import synced_message
from openstack_sync.utils import get_openstack_connection

LOG = logging.getLogger(__name__)

__all__ = [
    "CredentialKey",
    "FINALIZER",
    "HookConfig",
    "HookInputs",
    "SyncPlugin",
    "SyncResource",
    "add_resource_finalizer",
    "build_crd_hook_config",
    "get_openstack_connection",
    "group_by_credentials",
    "hook_enabled",
    "hook_inputs",
    "patch_resource_status",
    "release_deleted_resource_finalizer",
    "remove_resource_finalizer",
    "run_hook",
    "run_sync",
    "synced_message",
]


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def _patch_status(
    plugin: SyncPlugin, resource: SyncResource, sync_status: str, message: str
) -> None:
    patch_status(
        plugin.config,
        resource,
        sync_status,
        message,
        patch_resource_status=patch_resource_status,
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_sync(plugin: SyncPlugin, inputs: HookInputs) -> int:
    """Reconcile every CR, then prune. Returns a process exit code."""
    noun = plugin.noun
    resources = inputs.resources_to_reconcile
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

    finalizer_failures = _sync_live_finalizers(plugin, resources)
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
            conn = get_openstack_connection(secret_name, cloud_name)
        except Exception as exc:  # noqa: BLE001
            failed += len(group)
            _fail_group(plugin, group, f"OpenStack connection failed: {exc}")
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
            _fail_group(plugin, group, f"OpenStack API unavailable: {exc}")
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
                _patch_status(plugin, resource, "Failed", str(exc))
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
            _patch_status(plugin, resource, "Synced", synced_message(noun, notes))

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

    prune_code = _run_prune(plugin, inputs, connections)

    # A finalizer is only held while destructive, CR-scoped cleanup could still
    # be outstanding, so it is released once that cleanup has run. When
    # uses_finalizer() is false there is no such cleanup to wait for: any
    # finalizer still on a deleted CR is stale (left from when the plugin did
    # use one), and it must be released even if a best-effort prune could not
    # connect -- otherwise the CR is wedged in Terminating for a step it does
    # not depend on. When uses_finalizer() is true a failed prune keeps the
    # finalizer, because the cleanup it guards did not complete.
    if plugin.uses_finalizer() and prune_code != 0:
        return prune_code

    release_code = _release_deleted_finalizers(plugin, inputs.deleted_resources)
    return prune_code or release_code


def _fail_group(plugin: SyncPlugin, group: list[SyncResource], message: str) -> None:
    for resource in group:
        _patch_status(plugin, resource, "Failed", message)


def _resource_target(
    plugin: SyncPlugin, resource: SyncResource
) -> CustomResourceTarget | None:
    return resource_target(plugin.config, resource)


def _write_finalizer(
    plugin: SyncPlugin, resource: SyncResource, *, present: bool
) -> bool:
    return write_finalizer(
        plugin.config,
        resource,
        present=present,
        add_finalizer=add_resource_finalizer,
        remove_finalizer=remove_resource_finalizer,
    )


def _sync_live_finalizers(
    plugin: SyncPlugin, resources: list[SyncResource]
) -> set[tuple[str | None, str | None]]:
    return sync_live_finalizers(
        plugin,
        resources,
        add_finalizer=add_resource_finalizer,
        remove_finalizer=remove_resource_finalizer,
        fail_resource=lambda resource, message: _patch_status(
            plugin, resource, "Failed", message
        ),
    )


def _release_deleted_finalizers(
    plugin: SyncPlugin, resources: list[SyncResource]
) -> int:
    return release_deleted_finalizers(
        plugin.config,
        resources,
        release_finalizer=release_deleted_resource_finalizer,
    )


def _run_prune(
    plugin: SyncPlugin,
    inputs: HookInputs,
    connections: dict[CredentialKey, Any],
) -> int:
    return run_prune(
        plugin,
        inputs,
        connections,
        get_connection=get_openstack_connection,
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def run_hook(
    build_config: Callable[[], dict[str, Any]],
    run: Callable[[list[dict[str, Any]]], int],
) -> int:
    return _run_hook(
        build_config,
        run,
        argv=sys.argv,
        configure_logging=configure_logging,
        read_binding_context=read_binding_context,
    )
