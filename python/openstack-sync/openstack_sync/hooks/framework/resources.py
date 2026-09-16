"""Resource parsing and grouping helpers for OpenStack sync hooks."""

from __future__ import annotations

import logging
from typing import Any

from openstack_sync.hooks.framework.contracts import CredentialKey
from openstack_sync.hooks.framework.contracts import SyncResource

LOG = logging.getLogger(__name__)


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
