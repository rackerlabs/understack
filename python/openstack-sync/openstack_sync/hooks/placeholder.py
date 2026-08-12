#!/usr/bin/env python3
"""No-op shell-operator hook for the base openstack-sync image."""

from __future__ import annotations

import json
import sys

HOOK_CONFIG = {
    "configVersion": "v1",
    # Shell-operator requires at least one binding; this keeps the base image
    # valid without adding Kubernetes watches or plugin RBAC.
    "onStartup": 10,
}


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(HOOK_CONFIG, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
