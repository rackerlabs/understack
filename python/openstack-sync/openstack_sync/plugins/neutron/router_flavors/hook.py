#!/usr/bin/env python3
"""Reconcile Neutron router flavors and service profiles from CRD objects."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from openstack_sync.plugins.neutron.router_flavors import (
    router_flavors_common as common,
)
from openstack_sync.plugins.neutron.router_flavors.delete_router_flavors import (
    prune_removed_flavors,
)
from openstack_sync.plugins.neutron.router_flavors.update_router_flavors import (
    sync_flavor,
)


@dataclass(frozen=True)
class RouterFlavorResource:
    flavor: dict[str, Any]
    name: str | None
    namespace: str | None
    generation: int | None


def _router_flavor_binding() -> dict[str, Any]:
    binding: dict[str, Any] = {
        "name": common.CRD_BINDING_NAME,
        "apiVersion": common.CRD_API_VERSION,
        "kind": common.CRD_KIND,
        "executeHookOnEvent": ["Added", "Modified", "Deleted"],
        "jqFilter": ".spec",
        "includeSnapshotsFrom": [common.CRD_BINDING_NAME],
    }
    if common.CRD_NAMESPACE:
        binding["namespace"] = {
            "nameSelector": {
                "matchNames": [common.CRD_NAMESPACE],
            },
        }
    return binding


# This config is built when the hook process starts. Shell-operator reads it
# during pod startup by running this file with --config. Helm changes the pod
# checksum when hook values change, so Kubernetes restarts the pod and
# shell-operator reads the new config.
HOOK_CONFIG: dict[str, Any] = {
    "configVersion": "v1",
    "settings": {
        "executionMinInterval": "30s",
        "executionBurst": 1,
    },
}

if common.SYNC_ENABLED:
    HOOK_CONFIG["kubernetes"] = [_router_flavor_binding()]
    HOOK_CONFIG["schedule"] = [
        {
            "name": "hourly sync",
            "crontab": common.SYNC_CRONTAB,
            "includeSnapshotsFrom": [common.CRD_BINDING_NAME],
        }
    ]
else:
    # Shell-operator requires a hook to declare at least one executable binding.
    HOOK_CONFIG["onStartup"] = 10


def read_binding_context() -> list[dict[str, Any]]:
    path = os.environ.get("BINDING_CONTEXT_PATH")
    if not path:
        return []

    with open(path, encoding="utf-8") as context_file:
        contexts = json.load(context_file)

    if not isinstance(contexts, list):
        raise common.ConfigError("Shell-operator binding context must be a list")

    return common.validate_config(contexts, "Shell-operator binding context")


def _snapshot_items(contexts: list[dict[str, Any]]) -> list[Any] | None:
    for context in contexts:
        snapshots = context.get("snapshots")
        if not isinstance(snapshots, dict):
            continue
        items = snapshots.get(common.CRD_BINDING_NAME)
        if items is not None:
            if not isinstance(items, list):
                raise common.ConfigError(
                    f"Snapshot {common.CRD_BINDING_NAME} must be a list"
                )
            return items

    return None


def _synchronization_items(contexts: list[dict[str, Any]]) -> list[Any] | None:
    for context in contexts:
        if (
            context.get("binding") == common.CRD_BINDING_NAME
            and context.get("type") == "Synchronization"
        ):
            items = context.get("objects", [])
            if not isinstance(items, list):
                raise common.ConfigError(
                    f"Synchronization {common.CRD_BINDING_NAME} objects must be a list"
                )
            return items

    return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resource_from_object(obj: Any, source: str) -> RouterFlavorResource:
    if not isinstance(obj, dict):
        raise common.ConfigError(f"{source} object must be a Kubernetes object")

    spec = obj.get("spec")
    if not isinstance(spec, dict):
        raise common.ConfigError(f"{source} spec must be an object")

    flavor = dict(spec)
    metadata = obj.get("metadata", {})
    resource_name = None
    resource_namespace = None
    generation = None
    if isinstance(metadata, dict):
        resource_name = _string_or_none(metadata.get("name"))
        resource_namespace = _string_or_none(metadata.get("namespace"))
        generation = _int_or_none(metadata.get("generation"))

    if "name" not in flavor and isinstance(metadata, dict):
        flavor["name"] = resource_name

    return RouterFlavorResource(
        flavor=flavor,
        name=resource_name,
        namespace=resource_namespace,
        generation=generation,
    )


def _resources_from_items(items: list[Any], source: str) -> list[RouterFlavorResource]:
    resources: list[RouterFlavorResource] = []
    for index, item in enumerate(items):
        item_source = f"{source}[{index}]"
        if not isinstance(item, dict):
            raise common.ConfigError(f"{item_source} must be an object")

        obj = item.get("object", item)
        resources.append(_resource_from_object(obj, item_source))

    validated_flavors = common.validate_config(
        [resource.flavor for resource in resources],
        source,
    )
    validated_resources = [
        RouterFlavorResource(
            flavor=flavor,
            name=resource.name,
            namespace=resource.namespace,
            generation=resource.generation,
        )
        for resource, flavor in zip(resources, validated_flavors, strict=True)
    ]
    return sorted(
        validated_resources,
        key=lambda resource: str(resource.flavor.get("name", "")),
    )


def router_flavor_resources_from_binding_context(
    contexts: list[dict[str, Any]],
) -> list[RouterFlavorResource] | None:
    items = _snapshot_items(contexts)
    if items is not None:
        return _resources_from_items(items, f"Snapshot {common.CRD_BINDING_NAME}")

    items = _synchronization_items(contexts)
    if items is not None:
        return _resources_from_items(
            items,
            f"Synchronization {common.CRD_BINDING_NAME}",
        )

    return None


def flavors_from_binding_context(
    contexts: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    resources = router_flavor_resources_from_binding_context(contexts)
    if resources is None:
        return None
    return [resource.flavor for resource in resources]


def load_router_flavor_resources() -> list[RouterFlavorResource]:
    contexts = read_binding_context()
    if not contexts:
        raise common.ConfigError(
            "Shell-operator binding context is required to load "
            f"{common.CRD_KIND} objects"
        )

    resources = router_flavor_resources_from_binding_context(contexts)
    if resources is not None:
        return resources

    raise common.ConfigError(
        "Shell-operator binding context does not contain "
        f"{common.CRD_BINDING_NAME} snapshot or synchronization objects"
    )


def load_flavors() -> list[dict[str, Any]]:
    return [resource.flavor for resource in load_router_flavor_resources()]


def _utc_timestamp() -> str:
    timestamp = dt.datetime.now(dt.UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")


def _truncate_message(message: Any, max_length: int = 2048) -> str:
    text = str(message)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def patch_resource_status(
    resource: RouterFlavorResource,
    sync_status: str,
    message: str,
) -> None:
    if not common.STATUS_ENABLED:
        return

    if not resource.name:
        common.log(
            f"Unable to patch {common.CRD_KIND} status; "
            "Kubernetes metadata.name is missing"
        )
        return

    timestamp = _utc_timestamp()
    condition_status = "True" if sync_status == "Synced" else "False"
    reason = "ReconcileSucceeded" if sync_status == "Synced" else "ReconcileFailed"
    status = {
        "syncStatus": sync_status,
        "lastSyncTime": timestamp,
        "message": _truncate_message(message),
        "conditions": [
            {
                "type": "Synced",
                "status": condition_status,
                "reason": reason,
                "message": _truncate_message(message),
                "lastTransitionTime": timestamp,
            }
        ],
    }
    if resource.generation is not None:
        status["observedGeneration"] = resource.generation

    command = [
        "kubectl",
        "patch",
        common.CRD_RESOURCE,
        resource.name,
        "--type",
        "merge",
        "--subresource",
        "status",
        "-p",
        json.dumps({"status": status}, sort_keys=True),
    ]
    namespace = resource.namespace or common.CRD_NAMESPACE
    if namespace:
        command.extend(["-n", namespace])

    try:
        result = subprocess.run(  # noqa: S603,S607
            command,
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        common.log("WARNING: kubectl not found; unable to patch router flavor status")
        return

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "unknown error").strip()
        common.log(
            f"WARNING: failed to patch {common.CRD_KIND} status for "
            f"{resource.name}: {error}"
        )


def run() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--config":
        print(json.dumps(HOOK_CONFIG, indent=2))
        return 0

    if not common.SYNC_ENABLED:
        common.log("Router flavor sync is disabled")
        return 0

    resources = load_router_flavor_resources()
    flavors = [resource.flavor for resource in resources]
    conn = common.connect_openstack(os.environ.get("OS_CLOUD"))
    try:
        common.wait_for_openstack_network(conn)
    except Exception as exc:
        for resource in resources:
            patch_resource_status(resource, "Failed", f"Neutron API unavailable: {exc}")
        raise

    common.log(f"Found {len(flavors)} router flavor(s) to reconcile")
    failed_resources: list[RouterFlavorResource] = []
    for resource in resources:
        try:
            sync_flavor(conn, resource.flavor)
        except Exception as exc:
            failed_resources.append(resource)
            patch_resource_status(resource, "Failed", str(exc))
            flavor_name = common.get_value(
                resource.flavor,
                "name",
                default=resource.name or "<unknown>",
            )
            common.log(f"Failed to reconcile router flavor {flavor_name}: {exc}")
            continue
        patch_resource_status(
            resource,
            "Synced",
            "Successfully reconciled router flavor",
        )

    if failed_resources:
        common.log(
            "Skipping router flavor prune because "
            f"{len(failed_resources)} flavor(s) failed to reconcile"
        )
        return 1

    prune_removed_flavors(conn, flavors)

    common.log("Finished reconciling router flavors")
    return 0


def main() -> None:
    try:
        sys.exit(run())
    except Exception as exc:
        common.log(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
