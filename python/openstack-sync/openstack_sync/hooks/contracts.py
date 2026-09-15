"""Shared contracts for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openstack_sync.plugins.common import env_bool
from openstack_sync.plugins.common import env_float
from openstack_sync.plugins.common import env_int
from openstack_sync.plugins.common import env_required

#: A plugin's OpenStack credentials: ``(secret_name, cloud_name)``.
CredentialKey = tuple[str, str]

#: Finalizer used to keep CRs around until their OpenStack cleanup has finished.
FINALIZER = "openstack-sync.understack.rackspace.net/finalizer"


@dataclass(frozen=True)
class HookConfig:
    """Runtime configuration for one hook, built from its chart env prefix.

    The Helm chart injects ``<prefix>_ENABLED`` for each hook,
    ``<prefix>_CRD_API_VERSION``, ``<prefix>_CRD_KIND``,
    ``<prefix>_CRD_RESOURCE`` and ``<prefix>_STATUS_ENABLED`` for CRD hooks, and
    one variable per ``pluginData.<name>.hook.env`` key. ``HookConfig`` reads
    only the framework keys; plugins read custom prefixed env vars directly.

    Nothing here is read at import time. Shell-operator invokes ``--config``
    before the full environment is guaranteed to be present, so ``from_env`` is
    called from ``main`` and only once the hook is known to be enabled.
    """

    prefix: str
    crd_api_version: str
    crd_kind: str
    crd_resource: str
    binding_name: str
    namespace: str | None
    status_enabled: bool
    prune: bool
    sync_crontab: str
    ready_retries: int
    ready_delay: float

    @classmethod
    def from_env(cls, prefix: str, *, binding_name: str) -> HookConfig:
        """Build config from the environment the Helm chart injected."""
        return cls(
            prefix=prefix,
            crd_api_version=env_required(f"{prefix}_CRD_API_VERSION"),
            crd_kind=env_required(f"{prefix}_CRD_KIND"),
            crd_resource=env_required(f"{prefix}_CRD_RESOURCE"),
            binding_name=binding_name,
            namespace=os.environ.get("POD_NAMESPACE"),
            status_enabled=env_bool(f"{prefix}_STATUS_ENABLED", False),
            prune=env_bool(f"{prefix}_PRUNE", False),
            sync_crontab=os.environ.get(f"{prefix}_SYNC_CRONTAB", "").strip(),
            ready_retries=env_int(f"{prefix}_READY_RETRIES", 30),
            ready_delay=env_float(f"{prefix}_READY_DELAY", 10),
        )


@dataclass(frozen=True)
class SyncResource:
    """One CR with its resolved OpenStack credentials.

    ``spec`` is the CR spec with ``cloudCredentialsRef`` removed, so a plugin
    sees only its own fields.
    """

    spec: dict[str, Any]
    name: str | None
    namespace: str | None
    generation: int | None
    secret_name: str
    cloud_name: str
    current_status: dict[str, Any] | None = None
    finalizers: tuple[str, ...] = ()
    deletion_timestamp: str | None = None
    resource_version: str | None = None
    uid: str | None = None

    @property
    def credentials(self) -> CredentialKey:
        return (self.secret_name, self.cloud_name)

    @property
    def identity(self) -> str:
        """Key identifying this CR across a batch of events."""
        return self.uid or f"{self.namespace}/{self.name}"

    @property
    def has_finalizer(self) -> bool:
        """Return whether this CR already carries the framework finalizer."""
        return FINALIZER in self.finalizers

    @property
    def is_deleting(self) -> bool:
        """Return whether Kubernetes has started deleting this CR."""
        return self.deletion_timestamp is not None

    @property
    def display_name(self) -> str:
        """Return the OpenStack resource name, falling back to the CR name."""
        return str(self.spec.get("name") or self.name or "<unknown>")


@dataclass(frozen=True)
class HookInputs:
    """Binding context split by reconciliation purpose.

    The split matters: an event-driven run reconciles only the changed CRs, but
    must prune against the *full* desired set from the snapshot, and must know
    which credentials a deleted CR used in order to prune at all.

    ``prune_credentials`` is therefore the credentials of the changed and
    deleted CRs, not of the whole snapshot: a bare event for an unrelated CR
    must not sweep a cloud nothing asked about. The desired set each prune
    compares against stays the full one (see :meth:`SyncPlugin.prune`).

    ``unreadable_resources`` names the CRs the binding context described but
    that could not be read (see :class:`_ResourceReader`). They are absent from
    every other field, so the desired set is not known to be complete while it
    is non-empty.
    """

    resources_to_reconcile: list[SyncResource]
    desired_resources_for_prune: list[SyncResource]
    deleted_resources: list[SyncResource]
    prune_credentials: frozenset[CredentialKey]
    unreadable_resources: frozenset[str]
