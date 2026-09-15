"""Status helpers for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import logging
from collections.abc import Callable

from openstack_sync.hooks.framework.contracts import HookConfig
from openstack_sync.hooks.framework.contracts import SyncResource

LOG = logging.getLogger("openstack_sync.hooks.framework")


def patch_status(
    config: HookConfig,
    resource: SyncResource,
    sync_status: str,
    message: str,
    *,
    patch_resource_status: Callable[..., None],
) -> None:
    """Patch one CR status with the sync outcome."""
    if not resource.name:
        LOG.error(
            "Unable to patch %s status; Kubernetes metadata.name is missing",
            config.crd_kind,
        )
        return
    patch_resource_status(
        name=resource.name,
        namespace=resource.namespace or config.namespace,
        generation=resource.generation,
        sync_status=sync_status,
        message=message,
        crd_api_version=config.crd_api_version,
        crd_resource=config.crd_resource,
        crd_kind=config.crd_kind,
        status_enabled=config.status_enabled,
        current_status=resource.current_status,
    )


def synced_message(noun: str, notes: list[str]) -> str:
    """Return the Synced message, qualified by anything needing manual action.

    The resource really is converged, so the status stays Synced. Reporting a
    bare success while state diverges from the spec is how a broken resource
    stays invisible until it is used.
    """
    message = f"Successfully reconciled {noun}"
    if not notes:
        return message
    return f"{message}; needs manual action: {'; '.join(notes)}"
