"""Generic shell-operator hook utilities shared across all hooks.

Provides binding context I/O and CR status patching.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
from typing import Any

from kubernetes import client as k8s_client
from kubernetes.client.exceptions import ApiException

from openstack_sync.utils import load_kubernetes_config

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


def _desired_condition(
    sync_status: str, message: str, generation: int | None = None
) -> dict[str, Any]:
    """Return the Ready condition to write, without its timestamp.

    A CR has one notion of success, so it reports one condition. ``Ready`` is
    the name Kubernetes tooling expects: ``kubectl wait --for=condition=Ready``
    and kubernetes-entrypoint's ``custom_resources`` dependency both work off it.
    """
    synced = sync_status == "Synced"
    condition: dict[str, Any] = {
        "type": "Ready",
        "status": "True" if synced else "False",
        "reason": "Reconciled" if synced else "ReconcileError",
        "message": truncate_message(message),
    }
    if generation is not None:
        condition["observedGeneration"] = generation
    return condition


def _ready_condition(status: dict[str, Any]) -> dict[str, Any] | None:
    """Return the Ready condition in *status*, or None when it has none."""
    conditions = status.get("conditions")
    if not isinstance(conditions, list):
        return None
    for condition in conditions:
        if isinstance(condition, dict) and condition.get("type") == "Ready":
            return condition
    return None


def _transition_time(
    current: dict[str, Any] | None, condition_status: str, now: str
) -> str:
    """Return the ``lastTransitionTime`` to write.

    Kept from the existing condition while its ``status`` is unchanged, so the
    timestamp marks the last True/False flip rather than the last write. A
    message-only change leaves it alone.
    """
    if not current:
        return now
    existing = _ready_condition(current)
    if existing is None or existing.get("status") != condition_status:
        return now
    existing_time = existing.get("lastTransitionTime")
    return existing_time if isinstance(existing_time, str) and existing_time else now


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

    existing = _ready_condition(current)
    if existing is None:
        return False
    desired = _desired_condition(sync_status, truncated_message, generation)
    return all(existing.get(key) == value for key, value in desired.items())


#: Memoised CustomObjectsApi, so one config load serves every patch in a run.
_custom_objects_api: Any = None


def _customobjects_api() -> Any:
    """Return the shared ``CustomObjectsApi``, configuring the client once."""
    global _custom_objects_api
    if _custom_objects_api is None:
        load_kubernetes_config()
        _custom_objects_api = k8s_client.CustomObjectsApi()
    return _custom_objects_api


def crd_request_target(crd_api_version: str, crd_resource: str) -> tuple[str, str, str]:
    """Return ``(group, version, plural)`` for addressing a CR.

    Both arguments come from the hook's environment: ``<prefix>_CRD_API_VERSION``
    is ``<group>/<version>`` and ``<prefix>_CRD_RESOURCE`` is
    ``<plural>.<group>``.

    Raises:
        ValueError: When either value is not in the expected shape.
    """
    group, _, version = crd_api_version.partition("/")
    plural = crd_resource.partition(".")[0]
    if not group or not version or not plural:
        raise ValueError(
            f"cannot derive a CRD request target from "
            f"api_version={crd_api_version!r} and resource={crd_resource!r}"
        )
    return group, version, plural


def _api_error_detail(exc: ApiException, max_body: int = 512) -> str:
    """Return a one-line description of *exc* for a log message.

    The client hands over the apiserver's body as bytes, which is decoded first:
    formatting bytes directly logs a repr, where a newline is two characters and
    survives the flattening.
    """
    body = exc.body or ""
    if isinstance(body, bytes):
        body = body.decode("utf-8", "replace")
    body = str(body).strip().replace("\n", " ")
    detail = f"HTTP {exc.status} {exc.reason or ''}".strip()
    if not body:
        return detail
    return f"{detail}: {truncate_message(body, max_body)}"


def patch_resource_status(
    *,
    name: str,
    namespace: str | None,
    generation: int | None,
    sync_status: str,
    message: str,
    crd_api_version: str,
    crd_resource: str,
    crd_kind: str,
    status_enabled: bool,
    current_status: dict[str, Any] | None = None,
) -> None:
    """Patch the status subresource of a CR.

    A failed write is logged and swallowed: status is reporting, not the work
    itself. It logs at error level even so, because a CR that cannot report
    leaves anything waiting on its ``Ready`` condition stuck.

    Args:
        name: CR metadata.name.
        namespace: CR metadata.namespace. Required to address the object; the
            patch is skipped when it is absent.
        generation: CR metadata.generation for observedGeneration (optional).
        sync_status: One of ``"Synced"`` or ``"Failed"``.
        message: Human-readable detail for the status message.
        crd_api_version: CRD API version as ``<group>/<version>`` (e.g.
            ``neutron.understack.rackspace.net/v1alpha1``).
        crd_resource: Fully-qualified CRD resource name (e.g.
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

    if not namespace:
        LOG.error(
            "unable to patch %s status for %s; no namespace to address it in",
            crd_kind,
            name,
        )
        return

    try:
        group, version, plural = crd_request_target(crd_api_version, crd_resource)
    except ValueError as exc:
        LOG.error("unable to patch %s status for %s: %s", crd_kind, name, exc)
        return

    timestamp = utc_timestamp()
    condition = _desired_condition(sync_status, message, generation)
    condition["lastTransitionTime"] = _transition_time(
        current_status, str(condition["status"]), timestamp
    )
    status: dict[str, Any] = {
        "syncStatus": sync_status,
        "lastSyncTime": timestamp,
        "message": truncate_message(message),
        "conditions": [condition],
    }
    if generation is not None:
        status["observedGeneration"] = generation

    try:
        _customobjects_api().patch_namespaced_custom_object_status(
            group=group,
            version=version,
            namespace=namespace,
            plural=plural,
            name=name,
            body={"status": status},
            # Replaces the stored status field by field, and conditions
            # wholesale, so the CR keeps exactly one condition. Named here so
            # the request does not depend on the client's own default.
            _content_type="application/merge-patch+json",
        )
    except ApiException as exc:
        LOG.error(
            "failed to patch %s status for %s: %s",
            crd_kind,
            name,
            _api_error_detail(exc),
        )
    except Exception as exc:  # noqa: BLE001
        # Config load and transport failures land here, and so would a bad call
        # into the client -- hence the traceback.
        LOG.error(
            "failed to patch %s status for %s: %s: %s",
            crd_kind,
            name,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
