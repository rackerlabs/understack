#!/usr/bin/env python3
"""Reconcile Neutron router flavors and service profiles from JSON config."""

from __future__ import annotations

import json
import os
import sys

from understack_neutron_flavors import router_flavors_common as common
from understack_neutron_flavors.delete_router_flavors import prune_removed_flavors
from understack_neutron_flavors.update_router_flavors import sync_flavor

HOOK_CONFIG = {
    "configVersion": "v1",
    "onStartup": 1,
    "schedule": [
        {
            "name": "hourly sync",
            "crontab": common.SYNC_CRONTAB,
        }
    ],
    "settings": {
        "executionMinInterval": "30s",
        "executionBurst": 1,
    },
}


def run() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(HOOK_CONFIG, indent=2))
        return 0

    flavors = common.load_config(common.CONFIG_PATH)
    conn = common.connect_openstack(os.environ.get("OS_CLOUD"))
    common.wait_for_openstack_network(conn)

    common.log(f"Found {len(flavors)} router flavor(s) to reconcile")
    for flavor_config in flavors:
        sync_flavor(conn, flavor_config)

    prune_removed_flavors(conn, flavors)

    common.log("Finished reconciling router flavors")
    return 0


def main() -> None:
    try:
        sys.exit(run())
    except Exception as exc:
        common.log(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
