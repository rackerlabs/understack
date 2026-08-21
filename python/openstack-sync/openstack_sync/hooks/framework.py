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

from openstack_sync.hooks.common import configure_logging
from openstack_sync.hooks.common import patch_resource_status
from openstack_sync.hooks.common import read_binding_context
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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HookConfig:
    """Runtime configuration for one hook, built from its chart env prefix.

    The Helm chart injects ``<prefix>_ENABLED``, ``<prefix>_CRD_API_VERSION``,
    ``<prefix>_CRD_KIND``, ``<prefix>_CRD_RESOURCE`` and
    ``<prefix>_STATUS_ENABLED`` for every plugin that declares a CRD, plus one
    variable per ``pluginData.<name>.hook.env`` key. This dataclass is the
    Python half of that contract.

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

    @property
    def credentials(self) -> CredentialKey:
        return (self.secret_name, self.cloud_name)

    @property
    def display_name(self) -> str:
        """Return the OpenStack resource name, falling back to the CR name."""
        return str(self.spec.get("name") or self.name or "<unknown>")


@dataclass(frozen=True)
class HookInputs:
    """Binding context split by reconciliation purpose.

    The four-way split matters: an event-driven run reconciles only the changed
    CRs, but must prune against the *full* desired set from the snapshot, and
    must know which credentials a deleted CR used in order to prune at all.
    """

    resources_to_reconcile: list[SyncResource]
    desired_resources_for_prune: list[SyncResource]
    deleted_resources: list[SyncResource]
    prune_credentials: frozenset[CredentialKey]


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


def _resource_from_object(obj: dict[str, Any]) -> SyncResource:
    """Build a :class:`SyncResource` from a Kubernetes object.

    The CRD marks ``cloudCredentialsRef.secretName`` and ``.cloudName``
    required with ``minLength: 1``, so the API server rejects a CR missing them
    long before a hook sees it. They are read directly rather than re-validated.
    """
    spec = dict(obj["spec"])
    creds = spec.pop("cloudCredentialsRef")
    metadata = obj.get("metadata", {})

    return SyncResource(
        spec=spec,
        name=metadata.get("name"),
        namespace=metadata.get("namespace"),
        generation=metadata.get("generation"),
        secret_name=creds["secretName"],
        cloud_name=creds["cloudName"],
        current_status=obj.get("status"),
    )


def _resources_from_items(items: list[Any]) -> list[SyncResource]:
    """Build resources from snapshot or Synchronization items.

    Snapshot items wrap the object as ``{"object": {...}}``; Synchronization
    items are the object itself.
    """
    resources = [_resource_from_object(item.get("object", item)) for item in items]
    return sorted(resources, key=lambda r: str(r.spec.get("name", "")))


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
    contexts: list[dict[str, Any]], config: HookConfig
) -> tuple[list[SyncResource], list[SyncResource], frozenset[str]]:
    """Split this binding's Event contexts into changed and deleted resources."""
    changed: list[SyncResource] = []
    deleted: list[SyncResource] = []
    watch_events: set[str] = set()

    for context in contexts:
        if context.get("binding") != config.binding_name:
            continue
        if context.get("type") != "Event":
            continue

        watch_event = context["watchEvent"]
        watch_events.add(watch_event)

        obj = context.get("object")
        if not obj:
            LOG.warning(
                "%s %s event carries no object; ignoring it",
                config.crd_kind,
                watch_event,
            )
            continue

        resource = _resource_from_object(obj)
        if watch_event == "Deleted":
            deleted.append(resource)
        elif watch_event == "Modified" and _status_is_current(resource):
            LOG.info(
                "Skipping %s Modified event; generation %s is already Synced",
                resource.display_name,
                resource.generation,
            )
        else:
            changed.append(resource)

    changed.sort(key=lambda r: str(r.spec.get("name", "")))
    return changed, deleted, frozenset(watch_events)


def hook_inputs(contexts: list[dict[str, Any]], config: HookConfig) -> HookInputs:
    """Split a shell-operator binding context by reconciliation purpose.

    Event-driven runs reconcile only the changed CRs but prune against the full
    desired set from the accompanying snapshot. Schedule and Synchronization
    runs reconcile everything they are given.
    """
    changed, deleted, watch_events = _split_events(contexts, config)
    items = snapshot_items(contexts, config.binding_name)

    if watch_events:
        if items is None:
            raise ConfigError(
                f"Shell-operator {config.binding_name} event context does not "
                f"contain {config.binding_name} snapshot objects"
            )
        desired = _resources_from_items(items)
        # Only prune when something actually changed. A bare Added/Modified for
        # an unrelated CR must not trigger a prune sweep.
        if changed or deleted or "Deleted" in watch_events:
            prune_credentials = _credentials(desired) | _credentials(deleted)
        else:
            prune_credentials = frozenset()
        return HookInputs(changed, desired, deleted, prune_credentials)

    if items is None:
        items = synchronization_items(contexts, config.binding_name)
    if items is None:
        raise ConfigError(
            f"Shell-operator binding context does not contain "
            f"{config.binding_name} event, snapshot, or synchronization objects"
        )

    resources = _resources_from_items(items)
    return HookInputs(resources, resources, [], _credentials(resources))


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

        Optional: the default does nothing, which is correct for a plugin whose
        resources outlive their CR or that has nothing safe to delete.
        """
        LOG.debug("%s defines no prune step", type(self).__name__)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def _patch_status(
    plugin: SyncPlugin, resource: SyncResource, sync_status: str, message: str
) -> None:
    config = plugin.config
    if not resource.name:
        LOG.warning(
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

    grouped = group_by_credentials(resources)
    grouped_desired = group_by_credentials(inputs.desired_resources_for_prune)
    grouped_deleted = group_by_credentials(inputs.deleted_resources)
    connections: dict[CredentialKey, Any] = {}
    failed = 0

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

    if failed:
        # Pruning deletes resources absent from the desired set. A failed
        # reconcile means the desired set could not be established, so deleting
        # anything now risks removing a resource that should exist.
        LOG.error(
            "Skipping %s prune because %s resource(s) failed to reconcile",
            noun,
            failed,
        )
        return 1

    return _run_prune(plugin, inputs, grouped_desired, grouped_deleted, connections)


def _fail_group(plugin: SyncPlugin, group: list[SyncResource], message: str) -> None:
    for resource in group:
        _patch_status(plugin, resource, "Failed", message)


def _run_prune(
    plugin: SyncPlugin,
    inputs: HookInputs,
    grouped_desired: dict[CredentialKey, list[SyncResource]],
    grouped_deleted: dict[CredentialKey, list[SyncResource]],
    connections: dict[CredentialKey, Any],
) -> int:
    noun = plugin.noun
    prune_failed = False

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
            if not plugin.config.prune:
                continue
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
                [resource.spec for resource in desired],
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
        LOG.error("%s", exc)
        return 1
