#!/usr/bin/env python3
"""Shell-operator hook for OpenStack connectivity verification.

When ``OPENSTACK_PLACEHOLDER_ENABLED`` is ``true`` this hook runs on startup to
verify that the operator can authenticate against OpenStack. When it is ``false``
(the default) the hook still registers an ``onStartup`` binding, because
shell-operator requires every hook to declare at least one binding -- but it
does no work, so the base image needs no Kubernetes watches or extra RBAC.

This is a connectivity probe rather than a CR reconciler, so it uses only
``run_hook`` and not the :class:`~openstack_sync.hooks.framework.SyncPlugin`
machinery.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from openstack_sync.hooks.framework import hook_enabled
from openstack_sync.hooks.framework import run_hook
from openstack_sync.utils import get_openstack_connection

LOG = logging.getLogger(__name__)

ENV_PREFIX = "OPENSTACK_PLACEHOLDER"


def build_hook_config() -> dict[str, Any]:
    return {
        "configVersion": "v1",
        "settings": {"executionMinInterval": "30s", "executionBurst": 1},
        "onStartup": 10,
    }


def check_openstack_connectivity() -> None:
    """Authenticate against OpenStack and log the result.

    Credentials come from the Secret named by
    ``OPENSTACK_PLACEHOLDER_DEFAULT_SECRET`` using the cloud entry
    ``OPENSTACK_PLACEHOLDER_DEFAULT_CLOUD``.
    """
    secret_name = os.environ.get(f"{ENV_PREFIX}_DEFAULT_SECRET")
    cloud_name = os.environ.get(f"{ENV_PREFIX}_DEFAULT_CLOUD")

    LOG.info(
        "connectivity check: authenticating against cloud=%r secret=%r",
        cloud_name,
        secret_name,
    )
    conn = get_openstack_connection(secret_name, cloud_name)
    # check_token(str) -> bool confirms the token is valid and Keystone is
    # reachable, with no side effects.
    conn.identity.check_token(conn.auth_token)
    LOG.info("connectivity check: OK cloud=%r secret=%r", cloud_name, secret_name)


def main() -> int:
    def run(contexts: list[dict[str, Any]]) -> int:
        for context in contexts:
            # Shell-operator passes [{"binding": "onStartup"}] for startup runs.
            if context.get("binding") != "onStartup":
                continue
            if not hook_enabled(ENV_PREFIX):
                LOG.info(
                    "connectivity check: skipped (%s_ENABLED is not set)", ENV_PREFIX
                )
                continue
            try:
                check_openstack_connectivity()
            except Exception as exc:  # noqa: BLE001
                LOG.error("connectivity check FAILED: %s", exc)
                return 1
        return 0

    return run_hook(build_hook_config, run)


if __name__ == "__main__":
    sys.exit(main())
