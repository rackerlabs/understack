#!/usr/bin/env python3
"""Shell-operator hook for Neutron router flavor reconciliation."""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Any

from openstack_sync.hooks.common import configure_logging
from openstack_sync.hooks.common import int_or_none
from openstack_sync.hooks.common import patch_resource_status
from openstack_sync.hooks.common import read_binding_context
from openstack_sync.hooks.common import snapshot_items
from openstack_sync.hooks.common import string_or_none
from openstack_sync.hooks.common import synchronization_items
from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import env_bool
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.neutron.router_flavors.create import ServiceProfileCache
from openstack_sync.plugins.neutron.router_flavors.delete import prune_removed_flavors
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    crd_api_version,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    crd_binding_name,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import crd_kind
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    crd_namespace,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    crd_resource,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    prune_removed_flavors_enabled,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    status_enabled,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    wait_for_openstack_network,
)
from openstack_sync.plugins.neutron.router_flavors.update import sync_flavor
from openstack_sync.utils import get_openstack_connection

LOG = logging.getLogger(__name__)
CredentialKey = tuple[str, str]

# ---------------------------------------------------------------------------
# Resource dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouterFlavorResource:
    """A single NeutronRouterFlavor CR with its resolved credentials."""

    flavor: dict[str, Any]
    name: str | None
    namespace: str | None
    generation: int | None
    secret_name: str
    cloud_name: str
    current_status: dict[str, Any] | None = None


@dataclass(frozen=True)
class RouterFlavorHookInputs:
    """Parsed shell-operator context split by reconciliation purpose."""

    resources_to_reconcile: list[RouterFlavorResource]
    desired_resources_for_prune: list[RouterFlavorResource]
    deleted_resources: list[RouterFlavorResource]
    prune_credentials: frozenset[CredentialKey]


# ---------------------------------------------------------------------------
# Hook configuration
# ---------------------------------------------------------------------------


def build_hook_config() -> dict[str, Any]:
    hook_config: dict[str, Any] = {
        "configVersion": "v1",
        "settings": {
            "executionMinInterval": "30s",
            "executionBurst": 1,
        },
    }

    if not env_bool("NEUTRON_ROUTER_FLAVOR_ENABLED", False):
        # Shell-operator requires at least one binding.
        hook_config["onStartup"] = 10
        return hook_config

    sync_crontab = os.environ.get("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "").strip()
    namespace = os.environ.get("POD_NAMESPACE")
    binding_name = crd_binding_name()
    kubernetes_binding: dict[str, Any] = {
        "name": binding_name,
        "apiVersion": crd_api_version(),
        "kind": crd_kind(),
        "executeHookOnEvent": ["Added", "Modified", "Deleted"],
        "jqFilter": ".",
        "includeSnapshotsFrom": [binding_name],
        # Dedicated queue so a slow Neutron readiness wait or reconciliation
        # only delays this hook's own tasks, not other hooks sharing the
        # default "main" queue.
        "queue": binding_name,
    }
    if namespace:
        kubernetes_binding["namespace"] = {
            "nameSelector": {"matchNames": [namespace]},
        }

    hook_config["kubernetes"] = [kubernetes_binding]
    if sync_crontab:
        hook_config["schedule"] = [
            {
                "name": "hourly sync",
                "crontab": sync_crontab,
                "includeSnapshotsFrom": [binding_name],
                "queue": binding_name,
            }
        ]
    return hook_config


# ---------------------------------------------------------------------------
# Binding context parsing
# ---------------------------------------------------------------------------


def _required_cloud_credential(
    creds_ref: dict[str, Any],
    field: str,
    source: str,
) -> str:
    value = creds_ref.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(
            f"{source} spec.cloudCredentialsRef.{field} must be a non-empty string"
        )
    return value.strip()


def _resource_from_object(obj: Any, source: str) -> RouterFlavorResource:
    if not isinstance(obj, dict):
        raise ConfigError(f"{source} object must be a Kubernetes object")

    spec = obj.get("spec")
    if not isinstance(spec, dict):
        raise ConfigError(f"{source} spec must be an object")

    flavor = dict(spec)
    metadata = obj.get("metadata", {})
    resource_name = None
    resource_namespace = None
    generation = None
    if isinstance(metadata, dict):
        resource_name = string_or_none(metadata.get("name"))
        resource_namespace = string_or_none(metadata.get("namespace"))
        generation = int_or_none(metadata.get("generation"))
    raw_status = obj.get("status")
    current_status = raw_status if isinstance(raw_status, dict) else None

    try:
        creds_ref = flavor.pop("cloudCredentialsRef")
    except KeyError as exc:
        raise ConfigError(f"{source} spec.cloudCredentialsRef is required") from exc
    if not isinstance(creds_ref, dict):
        raise ConfigError(f"{source} spec.cloudCredentialsRef must be an object")
    secret_name = _required_cloud_credential(creds_ref, "secretName", source)
    cloud_name = _required_cloud_credential(creds_ref, "cloudName", source)

    return RouterFlavorResource(
        flavor=flavor,
        name=resource_name,
        namespace=resource_namespace,
        generation=generation,
        secret_name=secret_name,
        cloud_name=cloud_name,
        current_status=current_status,
    )


def _resources_from_items(items: list[Any], source: str) -> list[RouterFlavorResource]:
    resources: list[RouterFlavorResource] = []
    for index, item in enumerate(items):
        item_source = f"{source}[{index}]"
        if not isinstance(item, dict):
            raise ConfigError(f"{item_source} must be an object")
        obj = item.get("object", item)
        resources.append(_resource_from_object(obj, item_source))

    return sorted(resources, key=lambda r: str(r.flavor.get("name", "")))


def _credentials_for_resources(
    resources: list[RouterFlavorResource],
) -> frozenset[CredentialKey]:
    return frozenset(
        (resource.secret_name, resource.cloud_name) for resource in resources
    )


def _router_flavor_event_watch_events(
    contexts: list[dict[str, Any]],
) -> frozenset[str] | None:
    binding_name = crd_binding_name()
    watch_events: set[str] = set()
    for context in contexts:
        if context.get("binding") != binding_name or context.get("type") != "Event":
            continue
        watch_event = context.get("watchEvent")
        if not isinstance(watch_event, str) or not watch_event:
            raise ConfigError(
                f"{binding_name} event watchEvent must be a non-empty string"
            )
        watch_events.add(watch_event)
    return frozenset(watch_events) if watch_events else None


def _modified_event_status_is_current(resource: RouterFlavorResource) -> bool:
    status = resource.current_status
    return (
        resource.generation is not None
        and status is not None
        and status.get("syncStatus") == "Synced"
        and status.get("observedGeneration") == resource.generation
    )


def changed_router_flavor_resources_from_binding_context(
    contexts: list[dict[str, Any]],
) -> list[RouterFlavorResource] | None:
    binding_name = crd_binding_name()
    resources: list[RouterFlavorResource] = []
    saw_event = False
    for index, context in enumerate(contexts):
        if context.get("binding") != binding_name or context.get("type") != "Event":
            continue

        saw_event = True
        watch_event = context.get("watchEvent")
        if watch_event == "Deleted":
            continue
        if watch_event not in {"Added", "Modified"}:
            raise ConfigError(
                f"{binding_name} event watchEvent must be Added, Modified, or Deleted"
            )

        obj = context.get("object")
        if not obj:
            raise ConfigError(
                f"{watch_event} event {binding_name}[{index}] object is required"
            )
        resource = _resource_from_object(
            obj,
            f"{watch_event} event {binding_name}[{index}]",
        )
        if watch_event == "Modified" and _modified_event_status_is_current(resource):
            LOG.info(
                "Skipping router flavor %s Modified event; generation %s is already "
                "Synced",
                _resource_display_name(resource),
                resource.generation,
            )
            continue
        resources.append(resource)

    if not saw_event:
        return None
    return sorted(resources, key=lambda r: str(r.flavor.get("name", "")))


def deleted_router_flavor_resources_from_binding_context(
    contexts: list[dict[str, Any]],
) -> list[RouterFlavorResource]:
    binding_name = crd_binding_name()
    resources: list[RouterFlavorResource] = []
    for index, context in enumerate(contexts):
        if (
            context.get("binding") != binding_name
            or context.get("type") != "Event"
            or context.get("watchEvent") != "Deleted"
        ):
            continue
        obj = context.get("object")
        if not obj:
            LOG.warning(
                "Deleted %s event has no object; cannot use it for prune credentials",
                crd_kind(),
            )
            continue
        resources.append(
            _resource_from_object(
                obj,
                f"Deleted event {binding_name}[{index}]",
            )
        )

    return resources


def router_flavor_resources_from_binding_context(
    contexts: list[dict[str, Any]],
) -> list[RouterFlavorResource] | None:
    binding_name = crd_binding_name()
    items = snapshot_items(contexts, binding_name)
    if items is not None:
        return _resources_from_items(items, f"Snapshot {binding_name}")

    items = synchronization_items(contexts, binding_name)
    if items is not None:
        return _resources_from_items(items, f"Synchronization {binding_name}")

    return None


def router_flavor_hook_inputs_from_binding_context(
    contexts: list[dict[str, Any]],
) -> RouterFlavorHookInputs | None:
    binding_name = crd_binding_name()
    event_watch_events = _router_flavor_event_watch_events(contexts)
    changed_resources = changed_router_flavor_resources_from_binding_context(contexts)
    deleted_resources = deleted_router_flavor_resources_from_binding_context(contexts)

    if event_watch_events is not None:
        items = snapshot_items(contexts, binding_name)
        if items is None:
            raise ConfigError(
                f"Shell-operator {binding_name} event context does not contain "
                f"{binding_name} snapshot objects"
            )
        desired_resources = _resources_from_items(items, f"Snapshot {binding_name}")
        if changed_resources or deleted_resources or "Deleted" in event_watch_events:
            prune_credentials = _credentials_for_resources(
                desired_resources
            ) | _credentials_for_resources(deleted_resources)
        else:
            prune_credentials = frozenset()
        return RouterFlavorHookInputs(
            resources_to_reconcile=changed_resources or [],
            desired_resources_for_prune=desired_resources,
            deleted_resources=deleted_resources,
            prune_credentials=prune_credentials,
        )

    resources = router_flavor_resources_from_binding_context(contexts)
    if resources is not None:
        return RouterFlavorHookInputs(
            resources_to_reconcile=resources,
            desired_resources_for_prune=resources,
            deleted_resources=[],
            prune_credentials=_credentials_for_resources(resources),
        )

    return None


def load_router_flavor_hook_inputs(
    contexts: list[dict[str, Any]] | None = None,
) -> RouterFlavorHookInputs:
    if contexts is None:
        contexts = read_binding_context()
    if not contexts:
        raise ConfigError(
            f"Shell-operator binding context is required to load {crd_kind()} objects"
        )

    hook_inputs = router_flavor_hook_inputs_from_binding_context(contexts)
    if hook_inputs is not None:
        return hook_inputs

    raise ConfigError(
        f"Shell-operator binding context does not contain "
        f"{crd_binding_name()} event, snapshot, or synchronization objects"
    )


# ---------------------------------------------------------------------------
# Status patching
# ---------------------------------------------------------------------------


def patch_flavor_status(
    resource: RouterFlavorResource,
    sync_status: str,
    message: str,
) -> None:
    kind = crd_kind()
    if not resource.name:
        LOG.warning(
            "Unable to patch %s status; Kubernetes metadata.name is missing",
            kind,
        )
        return
    patch_resource_status(
        name=resource.name,
        namespace=resource.namespace or crd_namespace(),
        generation=resource.generation,
        sync_status=sync_status,
        message=message,
        crd_resource=crd_resource(),
        crd_kind=kind,
        status_enabled=status_enabled(),
        current_status=resource.current_status,
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def _resource_display_name(resource: RouterFlavorResource) -> str:
    return str(get_value(resource.flavor, "name", default=resource.name or "<unknown>"))


def _resources_by_credentials(
    resources: list[RouterFlavorResource],
) -> dict[CredentialKey, list[RouterFlavorResource]]:
    grouped: dict[CredentialKey, list[RouterFlavorResource]] = {}
    for resource in resources:
        key = (resource.secret_name, resource.cloud_name)
        grouped.setdefault(key, []).append(resource)
    return grouped


def _mark_resources_failed(
    resources: list[RouterFlavorResource],
    message: str,
) -> None:
    for resource in resources:
        patch_flavor_status(resource, "Failed", message)


def reconcile_router_flavor_resource(
    conn: Any, resource: RouterFlavorResource, profile_cache: ServiceProfileCache
) -> None:
    sync_flavor(conn, resource.flavor, profile_cache)


def reconcile_router_flavor_resources(
    resources: list[RouterFlavorResource],
    deleted_resources: list[RouterFlavorResource] | None = None,
    prune_resources: list[RouterFlavorResource] | None = None,
    prune_credentials: frozenset[CredentialKey] | None = None,
) -> int:
    deleted_resources = deleted_resources or []
    prune_resources = resources if prune_resources is None else prune_resources
    flavors = [resource.flavor for resource in resources]
    LOG.info("Found %s router flavor(s) to reconcile", len(flavors))

    grouped_resources = _resources_by_credentials(resources)
    grouped_prune_resources = _resources_by_credentials(prune_resources)
    deleted_resources_by_credentials = _resources_by_credentials(deleted_resources)
    if prune_credentials is None:
        prune_credentials = frozenset(grouped_resources)
    connections: dict[CredentialKey, Any] = {}
    failed_resources: list[RouterFlavorResource] = []

    for credentials in sorted(grouped_resources):
        credential_resources = grouped_resources[credentials]
        secret_name, cloud_name = credentials
        try:
            conn = get_openstack_connection(secret_name, cloud_name)
        except Exception as exc:  # noqa: BLE001
            failed_resources.extend(credential_resources)
            message = f"OpenStack connection failed: {exc}"
            _mark_resources_failed(credential_resources, message)
            LOG.error(
                "Failed to connect to OpenStack cloud=%r secret=%r: %s",
                cloud_name,
                secret_name,
                exc,
            )
            continue

        connections[credentials] = conn
        try:
            wait_for_openstack_network(conn)
        except Exception as exc:  # noqa: BLE001
            failed_resources.extend(credential_resources)
            _mark_resources_failed(
                credential_resources,
                f"Neutron API unavailable: {exc}",
            )
            LOG.error(
                "Neutron API unavailable for cloud=%r secret=%r: %s",
                cloud_name,
                secret_name,
                exc,
            )
            continue

        # Fetched lazily by driver once per credential group. ensure_profile()
        # appends newly created profiles into the same driver cache entry so a
        # later flavor with an identical meta_info spec reuses it.
        profile_cache: ServiceProfileCache = {}

        for resource in credential_resources:
            try:
                reconcile_router_flavor_resource(conn, resource, profile_cache)
            except Exception as exc:  # noqa: BLE001
                failed_resources.append(resource)
                patch_flavor_status(resource, "Failed", str(exc))
                LOG.error(
                    "Failed to reconcile router flavor %s: %s",
                    _resource_display_name(resource),
                    exc,
                )
                continue

            patch_flavor_status(
                resource,
                "Synced",
                "Successfully reconciled router flavor",
            )

    if failed_resources:
        LOG.error(
            "Skipping router flavor prune because %s flavor(s) failed to reconcile",
            len(failed_resources),
        )
        return 1

    prune_failed = False
    for credentials in sorted(prune_credentials):
        secret_name, cloud_name = credentials
        desired_resources = grouped_prune_resources.get(credentials, [])
        authoritative_empty_desired = (
            credentials in deleted_resources_by_credentials and not desired_resources
        )
        if not desired_resources and not authoritative_empty_desired:
            LOG.info(
                "Skipping router flavor prune for cloud=%r secret=%r; no desired "
                "router flavors are available",
                cloud_name,
                secret_name,
            )
            continue

        conn = connections.get(credentials)
        if conn is None:
            if not prune_removed_flavors_enabled():
                continue
            try:
                conn = get_openstack_connection(secret_name, cloud_name)
            except Exception as exc:  # noqa: BLE001
                prune_failed = True
                LOG.error(
                    "Failed to connect to OpenStack for router flavor prune "
                    "cloud=%r secret=%r: %s",
                    cloud_name,
                    secret_name,
                    exc,
                )
                continue
            try:
                wait_for_openstack_network(conn)
            except Exception as exc:  # noqa: BLE001
                prune_failed = True
                LOG.error(
                    "Neutron API unavailable for router flavor prune "
                    "cloud=%r secret=%r: %s",
                    cloud_name,
                    secret_name,
                    exc,
                )
                continue
            connections[credentials] = conn

        try:
            desired_flavors = [resource.flavor for resource in desired_resources]
            if authoritative_empty_desired:
                prune_removed_flavors(
                    conn,
                    desired_flavors,
                    authoritative_empty_desired=True,
                )
            else:
                prune_removed_flavors(conn, desired_flavors)
        except Exception as exc:  # noqa: BLE001
            prune_failed = True
            LOG.error(
                "Failed to prune router flavors cloud=%r secret=%r: %s",
                cloud_name,
                secret_name,
                exc,
            )

    if prune_failed:
        return 1

    if (
        not prune_credentials
        and not grouped_resources
        and not deleted_resources_by_credentials
    ):
        LOG.info(
            "Skipping router flavor prune; no router flavor credentials are available"
        )

    LOG.info("Finished reconciling router flavors")
    return 0


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(build_hook_config(), indent=2))
        return 0

    configure_logging()

    if not env_bool("NEUTRON_ROUTER_FLAVOR_ENABLED", False):
        LOG.info("Router flavor sync is disabled")
        return 0

    context_path = os.environ.get("BINDING_CONTEXT_PATH")
    if not context_path:
        return 0

    with open(context_path, encoding="utf-8") as f:
        raw = f.read()
    if not raw.strip():
        return 0

    try:
        binding_contexts = json.loads(raw)
    except json.JSONDecodeError as exc:
        LOG.error("failed to parse binding context: %s", exc)
        return 1

    try:
        if not isinstance(binding_contexts, list):
            raise ConfigError("Shell-operator binding context must be a list")
        hook_inputs = load_router_flavor_hook_inputs(binding_contexts)
        return reconcile_router_flavor_resources(
            hook_inputs.resources_to_reconcile,
            hook_inputs.deleted_resources,
            hook_inputs.desired_resources_for_prune,
            hook_inputs.prune_credentials,
        )
    except Exception as exc:  # noqa: BLE001
        LOG.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
