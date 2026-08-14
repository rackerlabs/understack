#!/usr/bin/env python3
"""Shell-operator hook for Neutron router flavor reconciliation."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from openstack_sync.hooks.common import dispatch_binding_contexts
from openstack_sync.hooks.common import int_or_none
from openstack_sync.hooks.common import patch_resource_status
from openstack_sync.hooks.common import read_binding_context
from openstack_sync.hooks.common import snapshot_items
from openstack_sync.hooks.common import string_or_none
from openstack_sync.hooks.common import synchronization_items
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
    DEFAULT_CLOUD,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    DEFAULT_SECRET,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    STATUS_ENABLED,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import (
    ConfigError,
)
from openstack_sync.plugins.neutron.router_flavors.router_flavors_common import log
from openstack_sync.plugins.neutron.router_flavors.update import sync_flavor
from openstack_sync.utils import get_openstack_connection

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

    is_sync_enabled = bool(
        os.environ.get("NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB", "").strip()
    )
    if not is_sync_enabled:
        # Shell-operator requires at least one binding.
        hook_config["onStartup"] = 10
        return hook_config

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
    hook_config["schedule"] = [
        {
            "name": "hourly sync",
            "crontab": os.environ["NEUTRON_ROUTER_FLAVOR_SYNC_CRONTAB"],
            "includeSnapshotsFrom": [CRD_BINDING_NAME],
        }
    ]
    return hook_config


HOOK_CONFIG = build_hook_config()


# ---------------------------------------------------------------------------
# Binding context parsing
# ---------------------------------------------------------------------------


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

    if "name" not in flavor and resource_name:
        flavor["name"] = resource_name

    creds_ref = flavor.pop("cloudCredentialsRef", {}) or {}
    secret_name = creds_ref.get("secretName") or DEFAULT_SECRET
    cloud_name = creds_ref.get("cloudName") or DEFAULT_CLOUD

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


def load_router_flavor_resources() -> list[RouterFlavorResource]:
    contexts = read_binding_context()
    if not contexts:
        raise ConfigError(
            f"Shell-operator binding context is required to load {CRD_KIND} objects"
        )

    items = snapshot_items(contexts, CRD_BINDING_NAME)
    if items is not None:
        return _resources_from_items(items, f"Snapshot {CRD_BINDING_NAME}")

    items = synchronization_items(contexts, CRD_BINDING_NAME)
    if items is not None:
        return _resources_from_items(items, f"Synchronization {CRD_BINDING_NAME}")

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
        log(f"Unable to patch {CRD_KIND} status; Kubernetes metadata.name is missing")
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
        log_fn=log,
    )


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


def reconcile_router_flavor(event: dict[str, Any]) -> None:
    """Reconcile a single NeutronRouterFlavor resource against OpenStack."""
    resource = _resource_from_object(event["object"], "event.object")
    conn = get_openstack_connection(resource.secret_name, resource.cloud_name)
    sync_flavor(conn, resource.flavor)


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(build_hook_config(), indent=2))
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
        print(f"failed to parse binding context: {exc}", file=sys.stderr)
        return 1

    return dispatch_binding_contexts(
        binding_contexts,
        CRD_BINDING_NAME,
        reconcile_router_flavor,
        log_fn=log,
    )


if __name__ == "__main__":
    sys.exit(main())
