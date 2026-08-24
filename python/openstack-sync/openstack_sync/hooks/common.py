"""Generic shell-operator hook utilities shared across all hooks.

Provides binding context I/O and status patching via kubectl.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import subprocess
import sys
from typing import Any

LOG = logging.getLogger(__name__)


def configure_logging() -> None:
    """Configure runtime hook logging without affecting --config output."""
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "info").upper(),
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
    """Read and parse the shell-operator binding context.

    An absent ``BINDING_CONTEXT_PATH`` or an empty file yields no contexts;
    shell-operator does invoke hooks with nothing to do. Malformed JSON raises
    :exc:`json.JSONDecodeError`, a :exc:`ValueError`.
    """
    path = os.environ.get("BINDING_CONTEXT_PATH")
    if not path:
        return []
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if not raw.strip():
        return []
    contexts = json.loads(raw)
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


def _condition_status(sync_status: str) -> str:
    return "True" if sync_status == "Synced" else "False"


def _condition_reason(sync_status: str) -> str:
    return "ReconcileSucceeded" if sync_status == "Synced" else "ReconcileFailed"


def _desired_condition(sync_status: str, message: str) -> dict[str, str]:
    return {
        "type": "Synced",
        "status": _condition_status(sync_status),
        "reason": _condition_reason(sync_status),
        "message": truncate_message(message),
    }


def _synced_condition(current: dict[str, Any]) -> dict[str, Any] | None:
    conditions = current.get("conditions")
    if not isinstance(conditions, list):
        return None
    for condition in conditions:
        if isinstance(condition, dict) and condition.get("type") == "Synced":
            return condition
    return None


def _status_is_current(
    current: dict[str, Any] | None,
    sync_status: str,
    message: str,
    generation: int | None,
) -> bool:
    """Return True when the existing CR status already matches desired state.

    Timestamp fields are intentionally ignored. Rewriting them on every no-op
    reconcile creates a Kubernetes Modified event and can requeue the hook.
    """
    if not current:
        return False

    truncated_message = truncate_message(message)
    if current.get("syncStatus") != sync_status:
        return False
    if current.get("message") != truncated_message:
        return False
    if generation is not None and current.get("observedGeneration") != generation:
        return False

    current_condition = _synced_condition(current)
    if current_condition is None:
        return False
    for key, value in _desired_condition(sync_status, truncated_message).items():
        if current_condition.get(key) != value:
            return False
    return True


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
    current_status: dict[str, Any] | None = None,
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
        current_status: Current CR status from the binding context. When it
            already matches the desired stable fields, the patch is skipped.
    """
    if not status_enabled:
        return

    if _status_is_current(current_status, sync_status, message, generation):
        LOG.debug(
            "skipping %s status patch for %s; status is already current",
            crd_kind,
            name,
        )
        return

    timestamp = utc_timestamp()
    condition = _desired_condition(sync_status, message)
    condition["lastTransitionTime"] = timestamp
    status: dict[str, Any] = {
        "syncStatus": sync_status,
        "lastSyncTime": timestamp,
        "message": truncate_message(message),
        "conditions": [condition],
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
