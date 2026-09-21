#!/usr/bin/env python3
"""Shell-operator hook for Neutron subnet pool reconciliation."""

from __future__ import annotations

import sys
from typing import Any

from openstack_sync.hooks.framework import CleanupPolicy
from openstack_sync.hooks.framework import HookConfig
from openstack_sync.hooks.framework import PruneRequest
from openstack_sync.hooks.framework import ReconcileResult
from openstack_sync.hooks.framework import SyncPlugin
from openstack_sync.hooks.framework import build_crd_hook_config
from openstack_sync.hooks.framework import hook_enabled
from openstack_sync.hooks.framework import hook_inputs
from openstack_sync.hooks.framework import run_hook
from openstack_sync.hooks.framework import run_sync
from openstack_sync.plugins.common import wait_for_openstack_network
from openstack_sync.plugins.neutron.subnet_pools import prune as prune_module
from openstack_sync.plugins.neutron.subnet_pools import reconcile as reconcile_module
from openstack_sync.plugins.neutron.subnet_pools.config import BINDING_NAME
from openstack_sync.plugins.neutron.subnet_pools.config import ENV_PREFIX
from openstack_sync.utils import pod_namespace


class SubnetPoolPlugin(SyncPlugin):
    """Sync NeutronSubnetPool CRs into Neutron subnet pools.

    The CR references Nautobot prefixes rather than raw CIDRs, so reconcile
    resolves those references against Nautobot before converging Neutron. The
    per-credential-group cache memoises the Nautobot client across every CR in
    one group.
    """

    noun = "subnet pool"

    def wait_for_api(self, conn: Any) -> None:
        wait_for_openstack_network(
            conn,
            retries=self.config.ready_retries,
            delay=self.config.ready_delay,
        )

    def reconcile(
        self, conn: Any, spec: dict[str, Any], cache: dict[str, Any]
    ) -> ReconcileResult:
        namespace = self.config.namespace or pod_namespace()
        return reconcile_module.sync_subnet_pool(conn, spec, namespace, cache)

    def prune_resources(self, conn: Any, request: PruneRequest) -> None:
        # The pool name is declared on the CR (spec.name is required), so the
        # desired names are read straight from the surviving specs -- no Nautobot
        # call. That keeps prune independent of Nautobot reachability, so an
        # outage can never make a live CR's pool look undesired.
        desired_names = reconcile_module.resolve_desired_names(request.desired_specs)
        prune_module.prune_removed_subnet_pools(
            conn,
            desired_names,
            authoritative_empty=request.authoritative_empty,
        )

    def cleanup_policy(self) -> CleanupPolicy:
        # NONE, not BEST_EFFORT_PRUNE like router flavors: a subnet pool can
        # have allocated subnets under it, so it must never be swept without the
        # finalizer, and unlike an orphaned service profile there is no
        # safe-every-cycle subset to reclaim. With prune off, deleting a CR
        # leaves its Neutron pool in place for an operator to drain and remove.
        if self.config.prune:
            return CleanupPolicy.FINALIZED_PRUNE
        return CleanupPolicy.NONE


def main() -> int:
    def run(contexts: list[dict[str, Any]]) -> int:
        if not hook_enabled(ENV_PREFIX):
            return 0
        config = HookConfig.from_env(ENV_PREFIX, binding_name=BINDING_NAME)
        return run_sync(SubnetPoolPlugin(config), hook_inputs(contexts, config))

    return run_hook(lambda: build_crd_hook_config(ENV_PREFIX, BINDING_NAME), run)


if __name__ == "__main__":
    sys.exit(main())
