"""Public facade for CR-driven OpenStack resource sync plugins.

A plugin supplies four things: how to wait for its OpenStack service, how to
converge one CR spec, an optional per-credential-group cache, and an optional
prune.

The implementation lives in sibling modules, while hooks and tests import
through this module. Keep public names here stable so operational monkeypatches
and the documented framework surface remain explicit.

See ``README.md`` for the steps to add a plugin.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from openstack_sync.hooks.framework.common import add_resource_finalizer
from openstack_sync.hooks.framework.common import configure_logging
from openstack_sync.hooks.framework.common import patch_resource_status
from openstack_sync.hooks.framework.common import read_binding_context
from openstack_sync.hooks.framework.common import release_deleted_resource_finalizer
from openstack_sync.hooks.framework.common import remove_resource_finalizer
from openstack_sync.hooks.framework.config import build_crd_hook_config
from openstack_sync.hooks.framework.config import hook_enabled
from openstack_sync.hooks.framework.contracts import FINALIZER
from openstack_sync.hooks.framework.contracts import CleanupPolicy
from openstack_sync.hooks.framework.contracts import CredentialKey
from openstack_sync.hooks.framework.contracts import HookConfig
from openstack_sync.hooks.framework.contracts import PruneRequest
from openstack_sync.hooks.framework.contracts import ReconcileResult
from openstack_sync.hooks.framework.contracts import SyncPlan
from openstack_sync.hooks.framework.contracts import SyncPlugin
from openstack_sync.hooks.framework.contracts import SyncResource
from openstack_sync.hooks.framework.entrypoint import run_hook as _run_hook
from openstack_sync.hooks.framework.finalizers import release_deleted_finalizers
from openstack_sync.hooks.framework.finalizers import sync_live_finalizers
from openstack_sync.hooks.framework.planner import hook_inputs
from openstack_sync.hooks.framework.pruning import PruneResult as _PruneResult
from openstack_sync.hooks.framework.pruning import run_prune
from openstack_sync.hooks.framework.resources import group_by_credentials
from openstack_sync.hooks.framework.runner import run_sync as _run_sync
from openstack_sync.hooks.framework.status import patch_status
from openstack_sync.hooks.framework.status import synced_message
from openstack_sync.utils import get_openstack_connection

__all__ = [
    "CleanupPolicy",
    "CredentialKey",
    "FINALIZER",
    "HookConfig",
    "PruneRequest",
    "ReconcileResult",
    "SyncPlan",
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
    plugin: SyncPlugin,
    resource: SyncResource,
    sync_status: str,
    message: str,
    extra_status: dict[str, Any] | None = None,
    reason: str | None = None,
) -> None:
    patch_status(
        plugin.config,
        resource,
        sync_status,
        message,
        patch_resource_status=patch_resource_status,
        extra_status=extra_status,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_sync(plugin: SyncPlugin, inputs: SyncPlan) -> int:
    return _run_sync(
        plugin,
        inputs,
        get_connection=get_openstack_connection,
        patch_status=_patch_status,
        sync_live_finalizers=_sync_live_finalizers,
        run_prune=_run_prune,
        release_deleted_finalizers=_release_deleted_finalizers,
    )


def _sync_live_finalizers(
    plugin: SyncPlugin,
    resources: list[SyncResource],
    cleanup_policy: CleanupPolicy,
) -> set[tuple[str | None, str | None]]:
    return sync_live_finalizers(
        plugin,
        resources,
        cleanup_policy=cleanup_policy,
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
    inputs: SyncPlan,
    connections: dict[CredentialKey, Any],
    cleanup_policy: CleanupPolicy,
) -> _PruneResult:
    return run_prune(
        plugin,
        inputs,
        connections,
        cleanup_policy=cleanup_policy,
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
