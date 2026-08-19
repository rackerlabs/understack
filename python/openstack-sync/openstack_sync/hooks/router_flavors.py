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
from openstack_sync.plugins.neutron.router_flavors.delete import prune_removed_flavors
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    CRD_API_VERSION,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    CRD_BINDING_NAME,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import CRD_KIND
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    CRD_NAMESPACE,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    CRD_RESOURCE,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    STATUS_ENABLED,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    wait_for_openstack_network,
)
from openstack_sync.plugins.neutron.router_flavors.update import sync_flavor
from openstack_sync.utils import get_openstack_connection

LOG = logging.getLogger(__name__)

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
    kubernetes_binding: dict[str, Any] = {
        "name": CRD_BINDING_NAME,
        "apiVersion": CRD_API_VERSION,
        "kind": CRD_KIND,
        "executeHookOnEvent": ["Added", "Modified", "Deleted"],
        "jqFilter": ".",
        "includeSnapshotsFrom": [CRD_BINDING_NAME],
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
                "includeSnapshotsFrom": [CRD_BINDING_NAME],
            }
        ]
    return hook_config


HOOK_CONFIG = build_hook_config()


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


def router_flavor_resources_from_binding_context(
    contexts: list[dict[str, Any]],
) -> list[RouterFlavorResource] | None:
    items = snapshot_items(contexts, CRD_BINDING_NAME)
    if items is not None:
        return _resources_from_items(items, f"Snapshot {CRD_BINDING_NAME}")

    items = synchronization_items(contexts, CRD_BINDING_NAME)
    if items is not None:
        return _resources_from_items(items, f"Synchronization {CRD_BINDING_NAME}")

    return None


def load_router_flavor_resources(
    contexts: list[dict[str, Any]] | None = None,
) -> list[RouterFlavorResource]:
    if contexts is None:
        contexts = read_binding_context()
    if not contexts:
        raise ConfigError(
            f"Shell-operator binding context is required to load {CRD_KIND} objects"
        )

    resources = router_flavor_resources_from_binding_context(contexts)
    if resources is not None:
        return resources

    raise ConfigError(
        f"Shell-operator binding context does not contain "
        f"{CRD_BINDING_NAME} snapshot or synchronization objects"
    )


# ---------------------------------------------------------------------------
# Status patching
# ---------------------------------------------------------------------------


def patch_flavor_status(
    resource: RouterFlavorResource,
    sync_status: str,
    message: str,
) -> None:
    if not resource.name:
        LOG.warning(
            "Unable to patch %s status; Kubernetes metadata.name is missing",
            CRD_KIND,
        )
        return
    patch_resource_status(
        name=resource.name,
        namespace=resource.namespace or CRD_NAMESPACE,
        generation=resource.generation,
        sync_status=sync_status,
        message=message,
        crd_resource=CRD_RESOURCE,
        crd_kind=CRD_KIND,
        status_enabled=STATUS_ENABLED,
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def _resource_display_name(resource: RouterFlavorResource) -> str:
    return str(get_value(resource.flavor, "name", default=resource.name or "<unknown>"))


def _resources_by_credentials(
    resources: list[RouterFlavorResource],
) -> dict[tuple[str, str], list[RouterFlavorResource]]:
    grouped: dict[tuple[str, str], list[RouterFlavorResource]] = {}
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


def reconcile_router_flavor_resource(conn: Any, resource: RouterFlavorResource) -> None:
    sync_flavor(conn, resource.flavor)


def reconcile_router_flavor(event: dict[str, Any]) -> None:
    """Reconcile a single NeutronRouterFlavor resource against OpenStack."""
    resource = _resource_from_object(event["object"], "event.object")
    conn = get_openstack_connection(resource.secret_name, resource.cloud_name)
    try:
        wait_for_openstack_network(conn)
        reconcile_router_flavor_resource(conn, resource)
    except Exception as exc:
        patch_flavor_status(resource, "Failed", str(exc))
        raise
    patch_flavor_status(resource, "Synced", "Successfully reconciled router flavor")


def reconcile_router_flavor_resources(resources: list[RouterFlavorResource]) -> int:
    flavors = [resource.flavor for resource in resources]
    LOG.info("Found %s router flavor(s) to reconcile", len(flavors))

    grouped_resources = _resources_by_credentials(resources)
    connections: dict[tuple[str, str], Any] = {}
    failed_resources: list[RouterFlavorResource] = []

    for credentials, credential_resources in grouped_resources.items():
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

        for resource in credential_resources:
            try:
                reconcile_router_flavor_resource(conn, resource)
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

    for credentials, credential_resources in grouped_resources.items():
        conn = connections[credentials]
        prune_removed_flavors(
            conn,
            [resource.flavor for resource in credential_resources],
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
        resources = load_router_flavor_resources(binding_contexts)
        return reconcile_router_flavor_resources(resources)
    except Exception as exc:  # noqa: BLE001
        LOG.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
