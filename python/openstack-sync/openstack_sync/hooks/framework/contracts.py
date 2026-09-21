"""Shared contracts for CR-driven OpenStack sync hooks."""

from __future__ import annotations

import logging
import os
from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from typing import Any

from openstack_sync.plugins.common import env_bool
from openstack_sync.plugins.common import env_float
from openstack_sync.plugins.common import env_int
from openstack_sync.plugins.common import env_required

LOG = logging.getLogger(__name__)

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
class SyncPlan:
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


@dataclass(frozen=True)
class PruneRequest:
    """One credential-scoped prune call with explicit safety metadata."""

    credentials: CredentialKey
    desired_specs: list[dict[str, Any]]
    authoritative_empty: bool


@dataclass(frozen=True)
class ReconcileResult:
    """Outcome of one CR's reconcile.

    ``notes`` are folded into the status message. ``extra_status`` is merged
    into the CR's status subresource verbatim, alongside the framework's own
    ``syncStatus``/``message``/``conditions`` fields -- the framework never
    inspects or validates its contents, so only the plugin and its CRD's
    status schema give it meaning.
    """

    notes: list[str] = field(default_factory=list)
    extra_status: dict[str, Any] | None = None


class CleanupPolicy(Enum):
    """How a plugin wants the framework to handle prune and finalizers."""

    NONE = (False, False)
    BEST_EFFORT_PRUNE = (True, False)
    FINALIZED_PRUNE = (True, True)

    def __init__(self, run_prune: bool, uses_finalizer: bool) -> None:
        self.run_prune = run_prune
        self.uses_finalizer = uses_finalizer


class SyncPlugin(ABC):
    """One CR-driven OpenStack resource sync.

    Subclasses implement ``wait_for_api`` and ``reconcile``; ``new_cache`` and
    ``prune_resources`` have usable defaults. ``run_sync`` drives the rest.
    """

    #: Human-readable singular noun used in logs and CR status messages.
    noun: str = "resource"

    def __init__(self, config: HookConfig) -> None:
        self.config = config

    @abstractmethod
    def wait_for_api(self, conn: Any) -> None:
        """Block until the OpenStack service this plugin targets is reachable."""

    @abstractmethod
    def reconcile(self, conn: Any, spec: dict[str, Any], cache: Any) -> ReconcileResult:
        """Converge one CR spec onto OpenStack.

        Returns a :class:`ReconcileResult` carrying human-readable notes about
        state that diverges from the spec but that the operator cannot correct
        on its own -- usually empty -- plus optional ``extra_status`` fields to
        merge into the CR's status subresource, for a plugin whose CRD reports
        structured status beyond syncStatus/message/conditions. Notes do not
        make the reconcile a failure; they qualify the success reported on the
        CR status. Raise to signal an actual failure.
        """

    def new_cache(self) -> Any:
        """Return a scratch cache shared by every CR in one credential group."""
        return {}

    def prune(
        self,
        conn: Any,
        desired_specs: list[dict[str, Any]],
        *,
        authoritative_empty: bool,
    ) -> None:
        """Delete resources whose CR was removed.

        *desired_specs* is every credential group's desired specs, not just
        those of the credentials *conn* authenticates as. A plugin prunes by its
        own ownership marker, which records no credential, and what a connection
        lists depends on its token, so a resource one group manages is reachable
        from another group's connection. The union is what keeps each group's
        prune to the resources no group asked for.

        One consequence: two credentials managing the same resource name keep
        each other's resource off the prune list. If they are separate clouds
        the resource leaks instead. That is the safer direction, since the
        alternative is deleting a resource whose CR still exists.

        *authoritative_empty* is scoped to this credential group, not to
        *desired_specs*: it says a CR using *these* credentials was deleted, so
        an empty desired set is a real one rather than a snapshot that could not
        be read. Because *desired_specs* is the union, it can be non-empty while
        this is True; a plugin only needs it to decide whether an empty
        *desired_specs* may be acted on.

        Optional: the default does nothing, which is correct for a plugin whose
        resources outlive their CR or that has nothing safe to delete.
        """
        LOG.debug("%s defines no prune step", type(self).__name__)

    def prune_resources(self, conn: Any, request: PruneRequest) -> None:
        """Prune with an explicit request object.

        Plugins should override this method when cleanup needs request metadata.
        The base implementation delegates to :meth:`prune`, which is enough for
        plugins that only need the desired specs and authoritative-empty signal.
        """
        self.prune(
            conn,
            request.desired_specs,
            authoritative_empty=request.authoritative_empty,
        )

    def cleanup_policy(self) -> CleanupPolicy:
        """Return this plugin's cleanup mode for the current configuration.

        By default, a real prune step becomes destructive, finalizer-backed
        cleanup only when the chart's prune flag is enabled. Plugins with
        best-effort prune behavior should override this method directly.
        """
        if self.config.prune and _plugin_has_prune_step(self):
            return CleanupPolicy.FINALIZED_PRUNE
        return CleanupPolicy.NONE

    def should_run_prune(self) -> bool:
        """Return whether this plugin's cleanup policy runs prune."""
        return self.cleanup_policy().run_prune

    def uses_finalizer(self) -> bool:
        """Return whether this plugin's cleanup policy uses finalizers."""
        return self.cleanup_policy().uses_finalizer


def _plugin_has_prune_step(plugin: SyncPlugin) -> bool:
    """Return whether *plugin* replaced the framework's no-op prune."""
    return (
        type(plugin).prune is not SyncPlugin.prune
        or type(plugin).prune_resources is not SyncPlugin.prune_resources
    )
