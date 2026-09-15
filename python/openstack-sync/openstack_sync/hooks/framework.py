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
import sys
from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
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
from openstack_sync.hooks.config import build_crd_hook_config
from openstack_sync.hooks.config import hook_enabled
from openstack_sync.hooks.contracts import FINALIZER
from openstack_sync.hooks.contracts import CredentialKey
from openstack_sync.hooks.contracts import HookConfig
from openstack_sync.hooks.contracts import HookInputs
from openstack_sync.hooks.contracts import SyncResource
from openstack_sync.hooks.resources import _credentials
from openstack_sync.hooks.resources import _dedupe_resources
from openstack_sync.hooks.resources import _resource_key
from openstack_sync.hooks.resources import _ResourceReader
from openstack_sync.hooks.resources import group_by_credentials
from openstack_sync.plugins.common import ConfigError
from openstack_sync.utils import get_openstack_connection

LOG = logging.getLogger(__name__)

__all__ = [
    "CredentialKey",
    "FINALIZER",
    "HookConfig",
    "HookInputs",
    "SyncPlugin",
    "SyncResource",
    "add_resource_finalizer",
    "build_crd_hook_config",
    "get_openstack_connection",
    "group_by_credentials",
    "hook_enabled",
    "hook_inputs",
    "patch_resource_status",
    "release_deleted_resource_finalizer",
    "remove_resource_finalizer",
    "run_hook",
    "run_sync",
    "synced_message",
]


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


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

    if saw_event_context:
        event_contexts = [
            context
            for context in contexts
            if context.get("binding") == config.binding_name
            and context.get("type") == "Event"
        ]
        items = snapshot_items(event_contexts, config.binding_name)
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

    items = snapshot_items(contexts, config.binding_name)
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
