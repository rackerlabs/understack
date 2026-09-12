#!/usr/bin/env python3
"""Shell-operator hook for Neutron network segment range reconciliation."""

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
from openstack_sync.plugins.neutron.segment_ranges import prune as prune_module
from openstack_sync.plugins.neutron.segment_ranges import reconcile as reconcile_module
from openstack_sync.plugins.neutron.segment_ranges.config import BINDING_NAME
from openstack_sync.plugins.neutron.segment_ranges.config import ENV_PREFIX


class SegmentRangePlugin(SyncPlugin):
    """Sync NeutronSegmentRange CRs into Neutron network segment ranges."""

    noun = "segment range"

    def wait_for_api(self, conn: Any) -> None:
        wait_for_openstack_network(
            conn,
            retries=self.config.ready_retries,
            delay=self.config.ready_delay,
        )

    def new_cache(self) -> reconcile_module.RangeCache:
        # Keyed by managed range name and shared across every CR in one
        # credential group, so the managed-range listing is fetched once and
        # reused by each reconcile and the prune.
        return {}

    def reconcile(
        self, conn: Any, spec: dict[str, Any], cache: reconcile_module.RangeCache
    ) -> list[str]:
        return reconcile_module.sync_segment_range(conn, spec, cache)

    def prune(
        self,
        conn: Any,
        desired_specs: list[dict[str, Any]],
        *,
        authoritative_empty: bool,
    ) -> None:
        if not self.config.prune:
            return
        prune_module.prune_removed_ranges(
            conn, desired_specs, authoritative_empty=authoritative_empty
        )


def main() -> int:
    def run(contexts: list[dict[str, Any]]) -> int:
        if not hook_enabled(ENV_PREFIX):
            return 0
        config = HookConfig.from_env(ENV_PREFIX, binding_name=BINDING_NAME)
        return run_sync(SegmentRangePlugin(config), hook_inputs(contexts, config))

    return run_hook(lambda: build_crd_hook_config(ENV_PREFIX, BINDING_NAME), run)


if __name__ == "__main__":
    sys.exit(main())
