#!/usr/bin/env python3
"""Shell-operator hook for Neutron router flavor reconciliation."""

from __future__ import annotations

import json
import os
import sys

HOOK_CONFIG = {
    "configVersion": "v1",
    "settings": {
        "executionMinInterval": "30s",
        "executionBurst": 1,
    },
}

# Check if sync is enabled via environment variable
SYNC_ENABLED = os.environ.get("NEUTRON_ROUTER_FLAVOR_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}

if SYNC_ENABLED:
    HOOK_CONFIG["kubernetes"] = [
        {
            "name": "neutron-router-flavors",
            "apiVersion": "neutron.understack.rackspace.net/v1alpha1",
            "kind": "NeutronRouterFlavor",
            "executeHookOnEvent": ["Added", "Modified", "Deleted"],
            "jqFilter": ".spec",
            "includeSnapshotsFrom": ["neutron-router-flavors"],
        }
    ]
    HOOK_CONFIG["schedule"] = [
        {
            "name": "hourly sync",
            "crontab": os.environ.get(
                "NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "0 * * * *"
            ),
            "includeSnapshotsFrom": ["neutron-router-flavors"],
        }
    ]
else:
    # Shell-operator requires at least one binding
    HOOK_CONFIG["onStartup"] = 10


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(HOOK_CONFIG, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
