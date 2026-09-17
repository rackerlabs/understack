#!/usr/bin/env python3
"""Shell-operator hook skeleton for Neutron subnet pool CRs."""

from __future__ import annotations

import logging
import sys
from typing import Any

from openstack_sync.hooks.framework import HookConfig
from openstack_sync.hooks.framework import SyncPlugin
from openstack_sync.hooks.framework import build_crd_hook_config
from openstack_sync.hooks.framework import hook_enabled
from openstack_sync.hooks.framework import hook_inputs
from openstack_sync.hooks.framework import run_hook
from openstack_sync.hooks.framework import run_sync

LOG = logging.getLogger(__name__)

ENV_PREFIX = "NEUTRON_SUBNET_POOL"
BINDING_NAME = "neutron-subnet-pools"


class SubnetPoolPlugin(SyncPlugin):
    """Read NeutronSubnetPool CRs without reconciling OpenStack state yet."""

    noun = "subnet pool"

    def wait_for_api(self, conn: Any) -> None:
        # Contract-only skeleton: credentials are resolved by the framework and
        # the CRs are readable before this runs. Neutron calls will be added
        # when resource creation semantics land.
        _ = conn

    def reconcile(self, conn: Any, spec: dict[str, Any], cache: Any) -> list[str]:
        _ = (conn, cache)
        LOG.info("Observed NeutronSubnetPool CR %s", spec.get("name", "<unnamed>"))
        return []


def main() -> int:
    def run(contexts: list[dict[str, Any]]) -> int:
        if not hook_enabled(ENV_PREFIX):
            return 0
        config = HookConfig.from_env(ENV_PREFIX, binding_name=BINDING_NAME)
        return run_sync(SubnetPoolPlugin(config), hook_inputs(contexts, config))

    return run_hook(lambda: build_crd_hook_config(ENV_PREFIX, BINDING_NAME), run)


if __name__ == "__main__":
    sys.exit(main())
