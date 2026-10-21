#!/usr/bin/env python3
"""Shell-operator hook for Neutron network segment range reconciliation."""

from __future__ import annotations

import sys
from typing import Any

from openstack_sync.hooks.framework import HookConfig
from openstack_sync.hooks.framework import ReconcileResult
from openstack_sync.hooks.framework import SyncPlugin
from openstack_sync.hooks.framework import build_crd_hook_config
from openstack_sync.hooks.framework import hook_enabled
from openstack_sync.hooks.framework import hook_inputs
from openstack_sync.hooks.framework import run_hook
from openstack_sync.hooks.framework import run_sync
from openstack_sync.plugins.common import wait_for_openstack_network
from openstack_sync.plugins.neutron.segment_ranges import reconcile as reconcile_module
from openstack_sync.plugins.neutron.segment_ranges.config import BINDING_NAME
from openstack_sync.plugins.neutron.segment_ranges.config import ENV_PREFIX


class SegmentRangePlugin(SyncPlugin):
    """Sync NeutronSegmentRange CRs into Neutron network segment ranges.

    A segment range is shared infrastructure that outlives any single CR: the
    plugin only ever finds, adopts, or creates one and never deletes it. It
    therefore defines no prune step, so the framework runs no cleanup and
    attaches no finalizer -- deleting a CR leaves its Neutron range in place for
    an operator to drain and remove.
    """

    noun = "segment range"

    def wait_for_api(self, conn: Any) -> None:
        wait_for_openstack_network(
            conn,
            retries=self.config.ready_retries,
            delay=self.config.ready_delay,
        )

    def new_cache(self) -> reconcile_module.RangeCache:
        # Keyed by range name and shared across every CR in one credential
        # group, so Neutron is listed once and reused by each reconcile in the
        # group.
        return {}

    def reconcile(
        self, conn: Any, spec: dict[str, Any], cache: reconcile_module.RangeCache
    ) -> ReconcileResult:
        notes = reconcile_module.sync_segment_range(conn, spec, cache)
        return ReconcileResult(notes=notes)


def main() -> int:
    def run(contexts: list[dict[str, Any]]) -> int:
        if not hook_enabled(ENV_PREFIX):
            return 0
        config = HookConfig.from_env(ENV_PREFIX, binding_name=BINDING_NAME)
        return run_sync(SegmentRangePlugin(config), hook_inputs(contexts, config))

    return run_hook(lambda: build_crd_hook_config(ENV_PREFIX, BINDING_NAME), run)


if __name__ == "__main__":
    sys.exit(main())
