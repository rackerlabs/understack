"""Framework for CR-driven OpenStack resource sync plugins.

A plugin supplies four things: how to wait for its OpenStack service, how to
converge one CR spec, an optional per-credential-group cache, and an optional
prune. This module supplies everything else -- shell-operator hook config,
credential grouping, connection setup, per-resource status patching, the
reconcile-then-prune ordering, and the exit code contract.

See ``README.md`` for the steps to add a plugin.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from openstack_sync.hooks.common import CustomResourceTarget
from openstack_sync.hooks.common import add_resource_finalizer
from openstack_sync.hooks.common import configure_logging
from openstack_sync.hooks.common import patch_resource_status
from openstack_sync.hooks.common import read_binding_context
from openstack_sync.hooks.common import release_deleted_resource_finalizer
from openstack_sync.hooks.common import remove_resource_finalizer
from openstack_sync.hooks.common import snapshot_items
from openstack_sync.hooks.common import synchronization_items
from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import env_bool
from openstack_sync.plugins.common import env_float
from openstack_sync.plugins.common import env_int
from openstack_sync.plugins.common import env_required
from openstack_sync.utils import get_openstack_connection

LOG = logging.getLogger(__name__)

#: A plugin's OpenStack credentials: ``(secret_name, cloud_name)``.
CredentialKey = tuple[str, str]

#: Finalizer used to keep CRs around until their OpenStack cleanup has finished.
FINALIZER = "openstack-sync.understack.rackspace.net/finalizer"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


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


def hook_enabled(prefix: str) -> bool:
    """Return whether the chart enabled the plugin behind *prefix*."""
    return env_bool(f"{prefix}_ENABLED", False)


def build_crd_hook_config(prefix: str, binding_name: str) -> dict[str, Any]:
    """Return the shell-operator hook config for a CRD-watching plugin.

    When the plugin is disabled the config carries only an ``onStartup``
    binding, because shell-operator requires every hook to declare at least
    one binding but the hook must not register Kubernetes watches it will not
    service.
    """
    hook_config: dict[str, Any] = {
        "configVersion": "v1",
        "settings": {"executionMinInterval": "30s", "executionBurst": 1},
    }

    if not hook_enabled(prefix):
        hook_config["onStartup"] = 10
        return hook_config

    config = HookConfig.from_env(prefix, binding_name=binding_name)
    binding: dict[str, Any] = {
        "name": config.binding_name,
        "apiVersion": config.crd_api_version,
        "kind": config.crd_kind,
        "executeHookOnEvent": ["Added", "Modified", "Deleted"],
        "jqFilter": ".",
        "includeSnapshotsFrom": [config.binding_name],
        # Dedicated queue so a slow readiness wait or reconcile only delays
        # this hook's own tasks, not other hooks sharing the default queue.
        "queue": config.binding_name,
    }
    if config.namespace:
        binding["namespace"] = {"nameSelector": {"matchNames": [config.namespace]}}

    hook_config["kubernetes"] = [binding]
    if config.sync_crontab:
        hook_config["schedule"] = [
            {
                "name": "periodic sync",
                "crontab": config.sync_crontab,
                "includeSnapshotsFrom": [config.binding_name],
                "queue": config.binding_name,
            }
        ]
    return hook_config


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


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


def group_by_credentials(
    resources: list[SyncResource],
) -> dict[CredentialKey, list[SyncResource]]:
    """Group *resources* by the credentials they authenticate with."""
    grouped: dict[CredentialKey, list[SyncResource]] = {}
    for resource in resources:
        grouped.setdefault(resource.credentials, []).append(resource)
    return grouped


def _credentials(resources: list[SyncResource]) -> frozenset[CredentialKey]:
    return frozenset(resource.credentials for resource in resources)


# ---------------------------------------------------------------------------
# Binding context -> resources
# ---------------------------------------------------------------------------


class _MalformedResourceError(Exception):
    """Raised when a watched object does not satisfy the CRD's spec contract."""


def _resource_identity(obj: dict[str, Any]) -> str:
    """Return ``namespace/name`` for *obj*, for logs and error messages."""
    metadata = obj.get("metadata") or {}
    name = metadata.get("name") or "<unnamed>"
    namespace = metadata.get("namespace")
    return f"{namespace}/{name}" if namespace else str(name)


def _resource_from_object(obj: dict[str, Any]) -> SyncResource:
    """Build a :class:`SyncResource` from a Kubernetes object.

    The spec is validated rather than assumed. The CRD marks
    ``spec.cloudCredentialsRef`` required and its ``secretName`` / ``cloudName``
    ``minLength: 1``, but that only binds writes: Kubernetes validates on
    admission, so an object stored before the schema required those fields is
    still served by the watch exactly as stored. Tightening a CRD neither
    invalidates nor migrates what already exists.
    """
    spec = obj.get("spec")
    if not isinstance(spec, dict):
        raise _MalformedResourceError("spec is missing or not an object")

    spec = dict(spec)
    creds = spec.pop("cloudCredentialsRef", None)
    if not isinstance(creds, dict):
        raise _MalformedResourceError(
            "spec.cloudCredentialsRef is missing or not an object"
        )

    secret_name = creds.get("secretName")
    cloud_name = creds.get("cloudName")
    if not secret_name or not cloud_name:
        raise _MalformedResourceError(
            "spec.cloudCredentialsRef must set both secretName and cloudName; "
            f"got secretName={secret_name!r}, cloudName={cloud_name!r}"
        )

    metadata = obj.get("metadata", {})
    raw_finalizers = metadata.get("finalizers", [])
    if isinstance(raw_finalizers, list):
        finalizers = tuple(str(value) for value in raw_finalizers)
    else:
        finalizers = ()

    return SyncResource(
        spec=spec,
        name=metadata.get("name"),
        namespace=metadata.get("namespace"),
        generation=metadata.get("generation"),
        secret_name=str(secret_name),
        cloud_name=str(cloud_name),
        current_status=obj.get("status"),
        finalizers=finalizers,
        deletion_timestamp=metadata.get("deletionTimestamp"),
        resource_version=metadata.get("resourceVersion"),
        uid=metadata.get("uid"),
    )


class _ResourceReader:
    """Reads watched objects into resources, naming the ones it cannot read.

    An object that fails validation is reported and dropped rather than raised
    past the batch, so one unusable CR does not stop the others from
    reconciling. Its identity is retained because a dropped CR leaves the
    desired set incomplete, which the caller needs in order to decide whether
    pruning is safe.

    One reader spans a whole binding context, so a CR that appears in both an
    event and the accompanying snapshot is reported once.
    """

    def __init__(self) -> None:
        self.unreadable: set[str] = set()

    def read(self, obj: dict[str, Any], description: str = "CR") -> SyncResource | None:
        """Return the resource for *obj*, or None when it cannot be read."""
        try:
            return _resource_from_object(obj)
        except _MalformedResourceError as exc:
            identity = _resource_identity(obj)
            self.unreadable.add(identity)
            LOG.error("Ignoring unreadable %s %s: %s", description, identity, exc)
            return None

    def read_all(
        self, items: list[Any]
    ) -> tuple[list[SyncResource], list[SyncResource]]:
        """Read snapshot or Synchronization items into live and deleting resources.

        Snapshot items wrap the object as ``{"object": {...}}``; Synchronization
        items are the object itself.
        """
        live: list[SyncResource] = []
        deleting: list[SyncResource] = []
        for item in items:
            resource = self.read(item.get("object", item))
            if resource is None:
                continue
            if resource.is_deleting:
                deleting.append(resource)
            else:
                live.append(resource)

        live.sort(key=lambda r: str(r.spec.get("name", "")))
        deleting.sort(key=lambda r: str(r.spec.get("name", "")))
        return live, deleting


def _resource_key(resource: SyncResource) -> tuple[str | None, str | None]:
    """Return a stable enough identity key for de-duplicating CR events."""
    return (resource.namespace, resource.name)


def _dedupe_resources(resources: list[SyncResource]) -> list[SyncResource]:
    """Return resources de-duplicated by namespace/name, preserving order."""
    seen: set[tuple[str | None, str | None]] = set()
    deduped: list[SyncResource] = []
    for resource in resources:
        key = _resource_key(resource)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(resource)
    return deduped


def _status_is_current(resource: SyncResource) -> bool:
    """Return True when the CR status already records this generation as Synced.

    The hook's own status patch surfaces as a Modified event carrying the same
    ``metadata.generation``. Without this check the hook would reconcile itself
    in a loop.
    """
    status = resource.current_status
    return (
        resource.generation is not None
        and status is not None
        and status.get("syncStatus") == "Synced"
        and status.get("observedGeneration") == resource.generation
    )


def _split_events(
    contexts: list[dict[str, Any]], config: HookConfig, reader: _ResourceReader
) -> tuple[list[SyncResource], list[SyncResource], bool]:
    """Split this binding's Event contexts into changed and deleted resources.

    Shell-operator can replay a backlog of events for one CR. Collapsing by CR
    identity keeps one logical resource from producing repeated finalizer,
    status, reconcile, and prune work in the same hook run.
    """
    changed: dict[str, SyncResource] = {}
    deleted: dict[str, SyncResource] = {}
    saw_event_context = False
    changed_events = 0
    changed_identities: set[str] = set()

    for context in contexts:
        if context.get("binding") != config.binding_name:
            continue
        if context.get("type") != "Event":
            continue
        saw_event_context = True

        watch_event = context.get("watchEvent")
        if not watch_event:
            LOG.warning("%s event carries no watchEvent; ignoring it", config.crd_kind)
            continue

        obj = context.get("object")
        if not obj:
            LOG.warning(
                "%s %s event carries no object; ignoring it",
                config.crd_kind,
                watch_event,
            )
            continue

        resource = reader.read(obj, f"{watch_event} CR")
        if resource is None:
            continue

        if resource.is_deleting or watch_event == "Deleted":
            deleted[resource.identity] = resource
            superseded = changed.pop(resource.identity, None)
            if superseded is not None:
                LOG.info(
                    "Not reconciling %s %s; a later event in this batch deleted it",
                    config.crd_kind,
                    superseded.display_name,
                )
        elif watch_event == "Modified" and _status_is_current(resource):
            LOG.info(
                "Skipping %s Modified event; generation %s is already Synced",
                resource.display_name,
                resource.generation,
            )
        else:
            deleted.pop(resource.identity, None)
            changed_events += 1
            changed_identities.add(resource.identity)
            changed[resource.identity] = resource

    if changed_events > len(changed_identities):
        LOG.info(
            "Collapsed %s %s changed event(s) across %s CR(s)",
            changed_events,
            config.crd_kind,
            len(changed_identities),
        )

    resources = sorted(changed.values(), key=lambda r: str(r.spec.get("name", "")))
    return resources, list(deleted.values()), saw_event_context


def hook_inputs(contexts: list[dict[str, Any]], config: HookConfig) -> HookInputs:
    """Split a shell-operator binding context by reconciliation purpose.

    Event-driven runs reconcile only the changed CRs but prune against the full
    desired set from the accompanying snapshot. Schedule and Synchronization
    runs reconcile everything they are given.
    """
    reader = _ResourceReader()
    changed, deleted, saw_event_context = _split_events(contexts, config, reader)
    items = snapshot_items(contexts, config.binding_name)

    if saw_event_context:
        if items is None:
            raise ConfigError(
                f"Shell-operator {config.binding_name} event context does not "
                f"contain {config.binding_name} snapshot objects"
            )
        desired, snapshot_deleted = reader.read_all(items)
        deleted = _dedupe_resources(deleted + snapshot_deleted)
        prune_credentials = _credentials(changed) | _credentials(deleted)
        return HookInputs(
            changed, desired, deleted, prune_credentials, frozenset(reader.unreadable)
        )

    if items is None:
        items = synchronization_items(contexts, config.binding_name)
    if items is None:
        raise ConfigError(
            f"Shell-operator binding context does not contain "
            f"{config.binding_name} event, snapshot, or synchronization objects"
        )

    resources, deleted = reader.read_all(items)
    return HookInputs(
        resources,
        resources,
        deleted,
        _credentials(resources) | _credentials(deleted),
        frozenset(reader.unreadable),
    )


# ---------------------------------------------------------------------------
# Plugin contract
# ---------------------------------------------------------------------------


class SyncPlugin(ABC):
    """One CR-driven OpenStack resource sync.

    Subclasses implement ``wait_for_api`` and ``reconcile``; ``new_cache`` and
    ``prune`` have usable defaults. ``run_sync`` drives the rest.
    """

    #: Human-readable singular noun used in logs and CR status messages.
    noun: str = "resource"

    def __init__(self, config: HookConfig) -> None:
        self.config = config

    @abstractmethod
    def wait_for_api(self, conn: Any) -> None:
        """Block until the OpenStack service this plugin targets is reachable."""

    @abstractmethod
    def reconcile(self, conn: Any, spec: dict[str, Any], cache: Any) -> list[str]:
        """Converge one CR spec onto OpenStack.

        Returns human-readable notes about state that diverges from the spec but
        that the operator cannot correct on its own -- usually empty. Notes do
        not make the reconcile a failure; they qualify the success reported on
        the CR status. Raise to signal an actual failure.
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

    def should_run_prune(self) -> bool:
        """Return whether ``run_sync`` should call this plugin's prune step.

        This asks a different question from :meth:`uses_finalizer`: whether
        there is *any* prune work to do this run, destructive or not. The
        default runs prune only when the chart prune flag is on and the plugin
        actually has a prune step. A plugin whose prune also does safe cleanup
        when destructive pruning is off overrides this to always run (see
        ``RouterFlavorPlugin``); such a run still installs no finalizer, because
        that cleanup does not need to block a CR's deletion.
        """
        return self.config.prune and _plugin_has_prune_step(self)

    def uses_finalizer(self) -> bool:
        """Return whether live CRs should be held by a finalizer until cleanup.

        This asks a different question from :meth:`should_run_prune`: whether
        deleting a CR must run a destructive, CR-scoped cleanup that Kubernetes
        has to wait for. The default installs a finalizer only when the chart
        prune flag is on and the plugin has a prune step. A plugin with a
        different cleanup model can override this, but leaving it tied to the
        destructive prune flag is why a plugin that prunes non-destructively
        with ``PRUNE=false`` still leaves its CRs free to delete immediately.
        """
        return self.config.prune and _plugin_has_prune_step(self)


def _plugin_has_prune_step(plugin: SyncPlugin) -> bool:
    """Return whether *plugin* replaced the framework's no-op prune."""
    return type(plugin).prune is not SyncPlugin.prune


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def _patch_status(
    plugin: SyncPlugin, resource: SyncResource, sync_status: str, message: str
) -> None:
    config = plugin.config
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


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_sync(plugin: SyncPlugin, inputs: HookInputs) -> int:
    """Reconcile every CR, then prune. Returns a process exit code."""
    noun = plugin.noun
    resources = inputs.resources_to_reconcile
    LOG.info("Found %s %s(s) to reconcile", len(resources), noun)

    connections: dict[CredentialKey, Any] = {}
    failed = 0

    unreadable = len(inputs.unreadable_resources)
    if unreadable:
        LOG.error(
            "Ignored %s unreadable %s(s): %s",
            unreadable,
            noun,
            ", ".join(sorted(inputs.unreadable_resources)),
        )

    finalizer_failures = _sync_live_finalizers(plugin, resources)
    if finalizer_failures:
        failed += len(finalizer_failures)
        resources = [
            resource
            for resource in resources
            if _resource_key(resource) not in finalizer_failures
        ]

    grouped = group_by_credentials(resources)

    for credentials in sorted(grouped):
        secret_name, cloud_name = credentials
        group = grouped[credentials]

        try:
            conn = get_openstack_connection(secret_name, cloud_name)
        except Exception as exc:  # noqa: BLE001
            failed += len(group)
            _fail_group(plugin, group, f"OpenStack connection failed: {exc}")
            LOG.error(
                "Failed to connect to OpenStack cloud=%r secret=%r: %s",
                cloud_name,
                secret_name,
                exc,
            )
            continue

        connections[credentials] = conn
        try:
            plugin.wait_for_api(conn)
        except Exception as exc:  # noqa: BLE001
            failed += len(group)
            _fail_group(plugin, group, f"OpenStack API unavailable: {exc}")
            LOG.error(
                "OpenStack API unavailable for cloud=%r secret=%r: %s",
                cloud_name,
                secret_name,
                exc,
            )
            continue

        # Shared across every CR in this credential group so lookups made for
        # one CR are reused by the next.
        cache = plugin.new_cache()

        for resource in group:
            try:
                notes = plugin.reconcile(conn, resource.spec, cache)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                _patch_status(plugin, resource, "Failed", str(exc))
                LOG.error(
                    "Failed to reconcile %s %s: %s", noun, resource.display_name, exc
                )
                continue

            if notes:
                LOG.warning(
                    "%s %s converged but needs manual action: %s",
                    noun.capitalize(),
                    resource.display_name,
                    "; ".join(notes),
                )
            _patch_status(plugin, resource, "Synced", synced_message(noun, notes))

    if failed or unreadable:
        # Pruning deletes resources absent from the desired set. A CR that
        # failed to reconcile or could not be read at all means the desired set
        # could not be established, so deleting anything now risks removing a
        # resource that should exist.
        LOG.error(
            "Skipping %s prune; %s failed to reconcile and %s could not be read",
            noun,
            failed,
            unreadable,
        )
        return 1

    prune_code = _run_prune(plugin, inputs, connections)

    # A finalizer is only held while destructive, CR-scoped cleanup could still
    # be outstanding, so it is released once that cleanup has run. When
    # uses_finalizer() is false there is no such cleanup to wait for: any
    # finalizer still on a deleted CR is stale (left from when the plugin did
    # use one), and it must be released even if a best-effort prune could not
    # connect -- otherwise the CR is wedged in Terminating for a step it does
    # not depend on. When uses_finalizer() is true a failed prune keeps the
    # finalizer, because the cleanup it guards did not complete.
    if plugin.uses_finalizer() and prune_code != 0:
        return prune_code

    release_code = _release_deleted_finalizers(plugin, inputs.deleted_resources)
    return prune_code or release_code


def _fail_group(plugin: SyncPlugin, group: list[SyncResource], message: str) -> None:
    for resource in group:
        _patch_status(plugin, resource, "Failed", message)


def _resource_target(
    plugin: SyncPlugin, resource: SyncResource
) -> CustomResourceTarget | None:
    """Return the Kubernetes patch target for *resource*, or None if unusable."""
    if not resource.name:
        LOG.error(
            "Unable to patch finalizers on %s; Kubernetes metadata.name is missing",
            plugin.config.crd_kind,
        )
        return None
    return CustomResourceTarget(
        name=resource.name,
        namespace=resource.namespace or plugin.config.namespace,
        api_version=plugin.config.crd_api_version,
        resource=plugin.config.crd_resource,
        kind=plugin.config.crd_kind,
    )


def _write_finalizer(
    plugin: SyncPlugin, resource: SyncResource, *, present: bool
) -> bool:
    """Add or remove the framework finalizer on a live CR.

    ``present`` says which state the CR should end in. This helper is for live
    CRs; deleted CRs use ``_release_deleted_finalizers`` so an already-gone
    object can be treated as success.
    """
    target = _resource_target(plugin, resource)
    if target is None:
        return False
    if present:
        return add_resource_finalizer(
            target=target,
            finalizer=FINALIZER,
            current_finalizers=list(resource.finalizers),
            resource_version=resource.resource_version,
        )
    return remove_resource_finalizer(
        target=target,
        finalizer=FINALIZER,
        current_finalizers=list(resource.finalizers),
    )


def _sync_live_finalizers(
    plugin: SyncPlugin, resources: list[SyncResource]
) -> set[tuple[str | None, str | None]]:
    """Make live CR finalizers match the plugin's current cleanup policy."""
    should_have_finalizer = plugin.uses_finalizer()
    failed: set[tuple[str | None, str | None]] = set()
    for resource in resources:
        if resource.has_finalizer == should_have_finalizer:
            continue
        if _write_finalizer(plugin, resource, present=should_have_finalizer):
            continue

        failed.add(_resource_key(resource))
        message = (
            "Unable to add finalizer before reconciling"
            if should_have_finalizer
            else "Unable to remove disabled finalizer before reconciling"
        )
        _patch_status(plugin, resource, "Failed", message)
    return failed


def _release_deleted_finalizers(
    plugin: SyncPlugin, resources: list[SyncResource]
) -> int:
    """Remove finalizers from deleted CRs after cleanup has succeeded."""
    failed = 0
    for resource in resources:
        if not resource.has_finalizer:
            continue
        target = _resource_target(plugin, resource)
        if target is None or not release_deleted_resource_finalizer(
            target=target,
            finalizer=FINALIZER,
            current_finalizers=list(resource.finalizers),
        ):
            failed += 1
    return 1 if failed else 0


def _run_prune(
    plugin: SyncPlugin,
    inputs: HookInputs,
    connections: dict[CredentialKey, Any],
) -> int:
    noun = plugin.noun
    prune_failed = False
    if not plugin.should_run_prune():
        LOG.info("Finished reconciling %s(s)", noun)
        return 0

    grouped_desired = group_by_credentials(inputs.desired_resources_for_prune)
    grouped_deleted = group_by_credentials(inputs.deleted_resources)

    # Every group's desired resources, because a resource is not private to the
    # credentials that manage it. A plugin prunes by its own ownership marker,
    # which records no credential, and what a connection lists depends on its
    # token: a system-scoped credential sees what a project-scoped one manages,
    # and every credential sees what is public. The union is what keeps each
    # group's prune to the resources no group asked for.
    all_desired_specs = [
        resource.spec for resource in inputs.desired_resources_for_prune
    ]

    for credentials in sorted(inputs.prune_credentials):
        secret_name, cloud_name = credentials
        desired = grouped_desired.get(credentials, [])
        # An empty desired set is only authoritative when we know a CR was
        # deleted; otherwise it may just be a snapshot we could not read, and
        # pruning against it would delete everything.
        authoritative_empty = credentials in grouped_deleted and not desired
        if not desired and not authoritative_empty:
            LOG.info(
                "Skipping %s prune for cloud=%r secret=%r; no desired resources",
                noun,
                cloud_name,
                secret_name,
            )
            continue

        conn = connections.get(credentials)
        if conn is None:
            try:
                conn = get_openstack_connection(secret_name, cloud_name)
                plugin.wait_for_api(conn)
            except Exception as exc:  # noqa: BLE001
                prune_failed = True
                LOG.error(
                    "Cannot reach OpenStack for %s prune cloud=%r secret=%r: %s",
                    noun,
                    cloud_name,
                    secret_name,
                    exc,
                )
                continue
            connections[credentials] = conn

        try:
            plugin.prune(
                conn,
                all_desired_specs,
                authoritative_empty=authoritative_empty,
            )
        except Exception as exc:  # noqa: BLE001
            prune_failed = True
            LOG.error(
                "Failed to prune %s cloud=%r secret=%r: %s",
                noun,
                cloud_name,
                secret_name,
                exc,
            )

    if prune_failed:
        return 1

    LOG.info("Finished reconciling %s(s)", noun)
    return 0


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def run_hook(
    build_config: Callable[[], dict[str, Any]],
    run: Callable[[list[dict[str, Any]]], int],
) -> int:
    """Handle the shell-operator calling convention shared by every hook.

    ``--config`` prints the hook config and exits; otherwise the binding
    context is read and handed to *run*. An empty or absent binding context is
    not an error -- shell-operator invokes hooks with no work to do.
    """
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(build_config(), indent=2))
        return 0

    configure_logging()

    try:
        contexts = read_binding_context()
    except ValueError as exc:
        LOG.error("failed to parse binding context: %s", exc)
        return 1

    if not contexts:
        return 0

    try:
        return run(contexts)
    except Exception as exc:  # noqa: BLE001
        # Type and traceback, not just the message: several builtins stringify
        # to something unusable on their own, a KeyError to nothing but the
        # missing key. This is the hook's last line, so whatever it omits is
        # lost.
        LOG.error("hook failed: %s: %s", type(exc).__name__, exc, exc_info=True)
        return 1
