#!/usr/bin/env python3
"""Shell-operator hook for Neutron router flavor reconciliation."""

from __future__ import annotations

import json
import os
import sys

TRUTHY_VALUES = {"1", "true", "yes", "on"}


def env_is_truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in TRUTHY_VALUES


def router_flavor_namespace() -> str | None:
    return (
        os.environ.get("NEUTRON_ROUTER_FLAVOR_NAMESPACE")
        or os.environ.get("POD_NAMESPACE")
        or None
    )


def build_hook_config() -> dict[str, object]:
    hook_config: dict[str, object] = {
        "configVersion": "v1",
        "settings": {
            "executionMinInterval": "30s",
            "executionBurst": 1,
        },
    }

    if not env_is_truthy("NEUTRON_ROUTER_FLAVOR_ENABLED"):
        # Shell-operator requires at least one binding.
        hook_config["onStartup"] = 10
        return hook_config

    kubernetes_binding: dict[str, object] = {
        "name": "neutron-router-flavors",
        "apiVersion": "neutron.understack.rackspace.net/v1alpha1",
        "kind": "NeutronRouterFlavor",
        "executeHookOnEvent": ["Added", "Modified", "Deleted"],
        "jqFilter": ".spec",
        "includeSnapshotsFrom": ["neutron-router-flavors"],
    }
    namespace = router_flavor_namespace()
    if namespace:
        kubernetes_binding["namespace"] = {
            "nameSelector": {
                "matchNames": [namespace],
            },
        }

    hook_config["kubernetes"] = [kubernetes_binding]
    hook_config["schedule"] = [
        {
            "name": "hourly sync",
            "crontab": os.environ.get(
                "NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *"
            ),
            "includeSnapshotsFrom": ["neutron-router-flavors"],
        }
    ]
    return hook_config


HOOK_CONFIG = build_hook_config()


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(build_hook_config(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
