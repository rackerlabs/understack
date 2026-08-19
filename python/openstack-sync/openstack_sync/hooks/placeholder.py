#!/usr/bin/env python3
"""Shell-operator hook for OpenStack connectivity verification.

When ``OPENSTACK_PLACEHOLDER_ENABLED`` is ``true`` this hook runs on startup
to verify that the operator can authenticate against OpenStack.  When the flag
is ``false`` (the default) the hook registers only an ``onStartup`` binding so
the base image satisfies shell-operator's requirement for at least one binding
without needing any Kubernetes watches or extra RBAC.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

from openstack_sync.hooks.common import configure_logging
from openstack_sync.utils import get_openstack_connection

LOG = logging.getLogger(__name__)
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
    ``OPENSTACK_PLACEHOLDER_DEFAULT_SECRET`` using
    the cloud entry ``OPENSTACK_PLACEHOLDER_DEFAULT_CLOUD``.

    Raises:
        Exception: Re-raises any connection failure after logging it.
    """
    secret_name = os.environ.get("OPENSTACK_PLACEHOLDER_DEFAULT_SECRET")
    cloud_name = os.environ.get("OPENSTACK_PLACEHOLDER_DEFAULT_CLOUD")

    LOG.info(
        "connectivity check: authenticating against cloud=%r secret=%r",
        cloud_name,
        secret_name,
    )
    conn = get_openstack_connection(secret_name, cloud_name)
    # Lightweight probe: check_token(str) -> bool confirms the token is valid
    # and Keystone is reachable without any side effects.
    conn.identity.check_token(conn.auth_token)
    LOG.info("connectivity check: OK cloud=%r secret=%r", cloud_name, secret_name)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(build_hook_config(), indent=2))
        return 0

    configure_logging()

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
        LOG.error("failed to parse binding context: %s", exc)
        return 1

    for context in binding_contexts:
        # Shell-operator passes [{"binding": "onStartup"}] for startup runs.
        if context.get("binding") == "onStartup":
            if not env_is_truthy("OPENSTACK_PLACEHOLDER_ENABLED"):
                LOG.info(
                    "connectivity check: skipped"
                    " (OPENSTACK_PLACEHOLDER_ENABLED is not set)"
                )
                continue
            try:
                check_openstack_connectivity()
            except Exception as exc:  # noqa: BLE001
                LOG.error("connectivity check FAILED: %s", exc)
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
