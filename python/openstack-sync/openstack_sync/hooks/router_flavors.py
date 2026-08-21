#!/usr/bin/env python3
"""Shell-operator hook for Neutron router flavor reconciliation."""

from __future__ import annotations

import sys
from typing import Any

from openstack_sync.hooks.framework import HookConfig
from openstack_sync.hooks.framework import SyncPlugin
from openstack_sync.hooks.framework import build_crd_hook_config
from openstack_sync.hooks.framework import hook_enabled
from openstack_sync.hooks.framework import hook_inputs
from openstack_sync.hooks.framework import run_hook
from openstack_sync.hooks.framework import run_sync
from openstack_sync.plugins.common import wait_for_openstack_network
from openstack_sync.plugins.neutron.router_flavors import prune as prune_module
from openstack_sync.plugins.neutron.router_flavors import reconcile as reconcile_module
from openstack_sync.plugins.neutron.router_flavors.config import BINDING_NAME
from openstack_sync.plugins.neutron.router_flavors.config import ENV_PREFIX


class RouterFlavorPlugin(SyncPlugin):
    """Sync NeutronRouterFlavor CRs into Neutron flavors and service profiles."""

    noun = "router flavor"

    def wait_for_api(self, conn: Any) -> None:
        wait_for_openstack_network(
            conn,
            retries=self.config.ready_retries,
            delay=self.config.ready_delay,
        )

    def new_cache(self) -> reconcile_module.ProfileCache:
        # Keyed by driver and shared across every flavor in one credential
        # group, so two flavors wanting the same profile share one lookup and
        # end up sharing one profile.
        return {}

    def reconcile(
        self, conn: Any, spec: dict[str, Any], cache: reconcile_module.ProfileCache
    ) -> list[str]:
        return reconcile_module.sync_flavor(conn, spec, cache)

    def prune(
        self,
        conn: Any,
        desired_specs: list[dict[str, Any]],
        *,
        authoritative_empty: bool,
    ) -> None:
        if not self.config.prune:
            return
        prune_module.prune_removed_flavors(
            conn, desired_specs, authoritative_empty=authoritative_empty
        )


def main() -> int:
    def run(contexts: list[dict[str, Any]]) -> int:
        if not hook_enabled(ENV_PREFIX):
            return 0
        config = HookConfig.from_env(ENV_PREFIX, binding_name=BINDING_NAME)
        return run_sync(RouterFlavorPlugin(config), hook_inputs(contexts, config))

    return run_hook(lambda: build_crd_hook_config(ENV_PREFIX, BINDING_NAME), run)


if __name__ == "__main__":
    sys.exit(main())
