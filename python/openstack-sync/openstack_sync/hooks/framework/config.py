"""Shell-operator configuration helpers for OpenStack sync hooks."""

from __future__ import annotations

from typing import Any

from openstack_sync.hooks.framework.contracts import HookConfig
from openstack_sync.plugins.common import env_bool


def hook_enabled(prefix: str) -> bool:
    """Return whether the chart enabled the plugin behind *prefix*."""
    return env_bool(f"{prefix}_ENABLED", False)


def build_crd_hook_config(prefix: str, binding_name: str) -> dict[str, Any]:
    """Return the shell-operator hook config for a CRD-watching plugin.

    When the plugin is disabled the config carries only an ``onStartup``
    binding, because shell-operator requires every hook to declare at least
    one binding but the hook must not register Kubernetes watches it will not
    service.
    """
    hook_config: dict[str, Any] = {
        "configVersion": "v1",
        "settings": {"executionMinInterval": "30s", "executionBurst": 1},
    }

    if not hook_enabled(prefix):
        hook_config["onStartup"] = 10
        return hook_config

    config = HookConfig.from_env(prefix, binding_name=binding_name)
    binding: dict[str, Any] = {
        "name": config.binding_name,
        "apiVersion": config.crd_api_version,
        "kind": config.crd_kind,
        "executeHookOnEvent": ["Added", "Modified", "Deleted"],
        "jqFilter": ".",
        "includeSnapshotsFrom": [config.binding_name],
        # Dedicated queue so a slow readiness wait or reconcile only delays
        # this hook's own tasks, not other hooks sharing the default queue.
        "queue": config.binding_name,
    }
    if config.namespace:
        binding["namespace"] = {"nameSelector": {"matchNames": [config.namespace]}}

    hook_config["kubernetes"] = [binding]
    if config.sync_crontab:
        hook_config["schedule"] = [
            {
                "name": "periodic sync",
                "crontab": config.sync_crontab,
                "includeSnapshotsFrom": [config.binding_name],
                "queue": config.binding_name,
            }
        ]
    return hook_config
