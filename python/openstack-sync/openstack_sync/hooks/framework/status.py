"""Status helpers for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import logging
from collections.abc import Callable

from openstack_sync.hooks.framework.contracts import HookConfig
from openstack_sync.hooks.framework.contracts import SyncResource

LOG = logging.getLogger(__name__)


def patch_status(
    config: HookConfig,
    resource: SyncResource,
    sync_status: str,
    message: str,
    *,
    patch_resource_status: Callable[..., None],
    extra_status: dict[str, object] | None = None,
    reason: str | None = None,
) -> None:
    """Patch one CR status with the sync outcome.

    ``extra_status`` and ``reason`` are passed straight through to
    *patch_resource_status*; see
    :class:`~openstack_sync.hooks.framework.contracts.ReconcileResult` for
    what ``extra_status`` is for. A failed reconcile has none to report, so
    that call site omits it.
    """
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
        extra_status=extra_status,
        reason=reason,
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
