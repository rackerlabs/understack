#!/usr/bin/env python3
"""Shell-operator hook for Ironic runbook connectivity verification.

When ``IRONIC_RUNBOOK_ENABLED`` is ``true`` this hook runs on startup to
verify that the operator can authenticate against OpenStack using the
credentials that will be used for Ironic runbook reconciliation. When the
flag is ``false`` (the default) the hook registers only an ``onStartup``
binding so the base image satisfies shell-operator's requirement for at
least one binding without needing any Kubernetes watches or extra RBAC.

This is a connectivity placeholder. Full reconciliation of ``IronicRunbook``
custom resources against Ironic (create/update/delete, trait management) is
not implemented here yet.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from openstack_sync.utils import get_openstack_connection

TRUTHY_VALUES = {"1", "true", "yes", "on"}


def env_is_truthy(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in TRUTHY_VALUES


def build_hook_config() -> dict[str, Any]:
    hook_config: dict[str, Any] = {
        "configVersion": "v1",
        "settings": {
            "executionMinInterval": "30s",
            "executionBurst": 1,
        },
        "onStartup": 10,
    }
    return hook_config


HOOK_CONFIG = build_hook_config()


def check_openstack_connectivity() -> None:
    """Attempt to authenticate against OpenStack and log the result.

    Reads credentials from the Kubernetes Secret named by
    ``IRONIC_RUNBOOK_DEFAULT_SECRET`` using the cloud entry
    ``IRONIC_RUNBOOK_DEFAULT_CLOUD``.

    Raises:
        Exception: Re-raises any connection failure after logging it.
    """
    secret_name = os.environ.get("IRONIC_RUNBOOK_DEFAULT_SECRET")
    cloud_name = os.environ.get("IRONIC_RUNBOOK_DEFAULT_CLOUD")

    print(
        f"connectivity check: authenticating against cloud={cloud_name!r} "
        f"secret={secret_name!r}",
        flush=True,
    )
    conn = get_openstack_connection(secret_name, cloud_name)
    # Lightweight probe: check_token(str) -> bool confirms the token is valid
    # and Keystone is reachable without any side effects.
    conn.identity.check_token(conn.auth_token)
    print(
        f"connectivity check: OK cloud={cloud_name!r} secret={secret_name!r}",
        flush=True,
    )


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(build_hook_config(), indent=2))
        return 0

    context_path = os.environ.get("BINDING_CONTEXT_PATH")
    if not context_path:
        return 0
    with open(context_path) as f:
        raw = f.read()
    if not raw.strip():
        return 0

    try:
        binding_contexts = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"failed to parse binding context: {exc}", file=sys.stderr)
        return 1

    for context in binding_contexts:
        # Shell-operator passes [{"binding": "onStartup"}] for startup runs.
        if context.get("binding") == "onStartup":
            if not env_is_truthy("IRONIC_RUNBOOK_ENABLED"):
                print(
                    "connectivity check: skipped"
                    " (IRONIC_RUNBOOK_ENABLED is not set)",
                    flush=True,
                )
                continue
            try:
                check_openstack_connectivity()
            except Exception as exc:  # noqa: BLE001
                print(
                    f"connectivity check FAILED: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
