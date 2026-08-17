#!/usr/bin/env python3
"""Shell-operator hook for Neutron router flavor reconciliation."""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from openstack_sync.utils import get_openstack_connection
from openstack_sync.utils import pod_namespace  # noqa: F401 — re-exported for tests

TRUTHY_VALUES = {"1", "true", "yes", "on"}


def env_is_truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in TRUTHY_VALUES


def router_flavor_namespace() -> str | None:
    return (
        os.environ.get("NEUTRON_ROUTER_FLAVOR_NAMESPACE")
        or os.environ.get("POD_NAMESPACE")
        or None
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def reconcile_router_flavor(event: dict[str, Any]) -> None:
    """Reconcile a single NeutronRouterFlavor resource against OpenStack.

    Reads ``spec.cloudCredentialsRef`` from the event to determine which
    Kubernetes Secret and which cloud entry to use.  No operator-level
    cloud configuration is required — each resource is self-describing.
    """
    obj = event["object"]
    spec = obj.get("spec", {})

    creds_ref = spec.get("cloudCredentialsRef", {})
    secret_name = creds_ref.get("secretName")
    cloud_name = creds_ref.get("cloudName")

    if not secret_name or not cloud_name:
        raise ValueError(
            f"NeutronRouterFlavor {obj.get('metadata', {}).get('name')!r} "
            "is missing spec.cloudCredentialsRef.secretName or .cloudName"
        )

    conn = get_openstack_connection(secret_name, cloud_name)  # noqa: F841

    # Full reconciliation logic (create/update/delete router flavor) will be
    # wired in here once the connection-per-resource pattern is established.
    # The connection object is available as `conn` for subsequent API calls.


# ---------------------------------------------------------------------------
# Hook configuration
# ---------------------------------------------------------------------------


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
        "jqFilter": ".",
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(build_hook_config(), indent=2))
        return 0

    raw = sys.stdin.read()
    if not raw.strip():
        return 0

    try:
        binding_contexts = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"failed to parse binding context: {exc}", file=sys.stderr)
        return 1

    for context in binding_contexts:
        binding = context.get("binding", "")
        if binding == "neutron-router-flavors":
            for item in context.get("objects", []):
                reconcile_router_flavor(item)

    return 0


if __name__ == "__main__":
    sys.exit(main())
