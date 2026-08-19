"""Generic shell-operator hook utilities shared across all hooks.

Provides binding context I/O, status patching via kubectl, and the
Synchronization/Event/Schedule dispatch loop that every hook needs.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any

LOG = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure runtime hook logging without affecting --config output."""
    logging.basicConfig(
        level=os.environ.get("OPENSTACK_SYNC_LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s:%(name)s:%(message)s",
        stream=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Type coercions
# ---------------------------------------------------------------------------


def string_or_none(value: Any) -> str | None:
    return None if value is None else str(value)


def int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Binding context I/O
# ---------------------------------------------------------------------------


def read_binding_context() -> list[dict[str, Any]]:
    """Read and parse the shell-operator binding context from BINDING_CONTEXT_PATH."""
    path = os.environ.get("BINDING_CONTEXT_PATH")
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        contexts = json.load(f)
    if not isinstance(contexts, list):
        raise ValueError("Shell-operator binding context must be a list")
    return contexts


def snapshot_items(
    contexts: list[dict[str, Any]],
    binding_name: str,
) -> list[Any] | None:
    """Return snapshot items for *binding_name* from *contexts*, or None."""
    for context in contexts:
        snapshots = context.get("snapshots")
        if not isinstance(snapshots, dict):
            continue
        items = snapshots.get(binding_name)
        if items is not None:
            if not isinstance(items, list):
                raise ValueError(f"Snapshot {binding_name} must be a list")
            return items
    return None


def synchronization_items(
    contexts: list[dict[str, Any]],
    binding_name: str,
) -> list[Any] | None:
    """Return Synchronization objects for *binding_name* from *contexts*, or None."""
    for context in contexts:
        if (
            context.get("binding") == binding_name
            and context.get("type") == "Synchronization"
        ):
            items = context.get("objects", [])
            if not isinstance(items, list):
                raise ValueError(
                    f"Synchronization {binding_name} objects must be a list"
                )
            return items
    return None


# ---------------------------------------------------------------------------
# Status patching
# ---------------------------------------------------------------------------


def utc_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 string with Z suffix."""
    timestamp = dt.datetime.now(dt.UTC).replace(microsecond=0)
    return timestamp.isoformat().replace("+00:00", "Z")


def truncate_message(message: Any, max_length: int = 2048) -> str:
    """Truncate *message* to *max_length* characters, appending '...' if cut."""
    text = str(message)
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."


def patch_resource_status(
    *,
    name: str,
    namespace: str | None,
    generation: int | None,
    sync_status: str,
    message: str,
    crd_resource: str,
    crd_kind: str,
    status_enabled: bool,
) -> None:
    """Patch the status subresource of a CR via kubectl.

    Args:
        name: CR metadata.name.
        namespace: CR metadata.namespace (optional).
        generation: CR metadata.generation for observedGeneration (optional).
        sync_status: One of ``"Synced"`` or ``"Failed"``.
        message: Human-readable detail for the status message.
        crd_resource: Fully-qualified CRD resource name for kubectl (e.g.
            ``neutronrouterflavors.neutron.understack.rackspace.net``).
        crd_kind: CRD kind used in log messages (e.g. ``NeutronRouterFlavor``).
        status_enabled: When False the function returns immediately.
    """
    if not status_enabled:
        return

    timestamp = utc_timestamp()
    condition_status = "True" if sync_status == "Synced" else "False"
    reason = "ReconcileSucceeded" if sync_status == "Synced" else "ReconcileFailed"
    status: dict[str, Any] = {
        "syncStatus": sync_status,
        "lastSyncTime": timestamp,
        "message": truncate_message(message),
        "conditions": [
            {
                "type": "Synced",
                "status": condition_status,
                "reason": reason,
                "message": truncate_message(message),
                "lastTransitionTime": timestamp,
            }
        ],
    }
    if generation is not None:
        status["observedGeneration"] = generation

    command = [
        "kubectl",
        "patch",
        crd_resource,
        name,
        "--type",
        "merge",
        "--subresource",
        "status",
        "-p",
        json.dumps({"status": status}, sort_keys=True),
    ]
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
        LOG.warning("kubectl not found; unable to patch %s status", crd_kind)
        return

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "unknown error").strip()
        LOG.warning("failed to patch %s status for %s: %s", crd_kind, name, error)


# ---------------------------------------------------------------------------
# Binding context dispatch loop
# ---------------------------------------------------------------------------


def dispatch_binding_contexts(
    binding_contexts: list[dict[str, Any]],
    binding_name: str,
    reconcile_fn: Callable[[dict[str, Any]], None],
) -> int:
    """Dispatch each object in *binding_contexts* to *reconcile_fn*.

    Handles the three shell-operator context types:
    - ``Synchronization``: full object list on startup
    - ``Event``: single Added/Modified/Deleted event (Deleted is skipped)
    - Schedule / other: objects from the snapshots map

    Args:
        binding_contexts: Parsed list from the shell-operator binding context.
        binding_name: The binding name to filter on.
        reconcile_fn: Called with each individual event dict ``{"object": ...}``.

    Returns:
        0 on success, 1 if any reconciliation raises.
    """
    failed = False

    for context in binding_contexts:
        binding = context.get("binding", "")
        context_type = context.get("type", "")

        if context_type == "Synchronization":
            if binding != binding_name:
                continue
            for item in context.get("objects", []):
                try:
                    reconcile_fn(item)
                except Exception as exc:  # noqa: BLE001
                    LOG.error("reconcile failed: %s", exc)
                    failed = True

        elif context_type == "Event":
            if binding != binding_name:
                continue
            if context.get("watchEvent") == "Deleted":
                continue
            obj = context.get("object")
            if obj:
                try:
                    reconcile_fn({"object": obj})
                except Exception as exc:  # noqa: BLE001
                    LOG.error("reconcile failed: %s", exc)
                    failed = True

        else:
            # Schedule bindings use the schedule's name, not the Kubernetes
            # binding name. The desired objects live in the snapshots map.
            snapshots = context.get("snapshots", {})
            for item in snapshots.get(binding_name, []):
                try:
                    reconcile_fn(item)
                except Exception as exc:  # noqa: BLE001
                    LOG.error("reconcile failed: %s", exc)
                    failed = True

    return 1 if failed else 0
