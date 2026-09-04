"""Reconcile an IronicRunbook CR onto Ironic."""

from __future__ import annotations

import json
import logging
from typing import Any

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import get_value
from openstack_sync.plugins.ironic.runbooks import client
from openstack_sync.plugins.ironic.runbooks.markers import is_managed_runbook
from openstack_sync.plugins.ironic.runbooks.markers import managed_extra
from openstack_sync.plugins.ironic.runbooks.markers import runbook_extra

LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Spec -> Ironic payload
# ---------------------------------------------------------------------------


def validate_spec(spec: dict[str, Any]) -> str:
    """Return the runbook name once the spec is valid."""
    name = str(spec.get("runbookName") or "")
    if not name:
        raise ConfigError("spec.runbookName must be set")
    if spec.get("public") and spec.get("owner"):
        raise ConfigError(
            f"Runbook {name!r} sets both public and owner. Ironic does not allow "
            "an owner on a public runbook. Drop spec.owner to share it with every "
            "project, or set spec.public to false to keep it owned."
        )
    return name


def _step_payload(index: int, step: Any) -> dict[str, Any]:
    """Return one CR step as Ironic's runbook step."""
    if not isinstance(step, dict):
        raise ConfigError(f"spec.steps[{index}] must be an object, got {step!r}")

    missing = [key for key in ("interface", "step", "order") if step.get(key) is None]
    if missing:
        raise ConfigError(
            f"spec.steps[{index}] is missing required field(s): {', '.join(missing)}"
        )

    try:
        order = int(step["order"])
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"spec.steps[{index}].order must be an integer, got {step['order']!r}"
        ) from exc

    return {
        "interface": str(step["interface"]),
        "step": str(step["step"]),
        "args": step.get("args") or {},
        "order": order,
    }


def desired_steps(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the runbook steps *spec* describes, in Ironic's shape."""
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ConfigError("spec.steps must be a non-empty list")
    return [_step_payload(index, step) for index, step in enumerate(steps)]


def canonical_steps(steps: Any) -> list[tuple[str, str, str, str]]:
    """Return *steps* as an order-insensitive comparison key."""
    if not isinstance(steps, list):
        return []
    return sorted(
        (
            str(step.get("interface", "")),
            str(step.get("step", "")),
            str(step.get("order", "")),
            json.dumps(step.get("args") or {}, sort_keys=True),
        )
        for step in steps
        if isinstance(step, dict)
    )


def desired_extra(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the ``extra`` to store, with the ownership markers merged in."""
    return managed_extra(spec.get("extra") or {})


def desired_traits(spec: dict[str, Any]) -> list[str]:
    """Return the traits *spec* asks for."""
    return [str(trait) for trait in spec.get("traits") or []]


def build_payload(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the body that creates the runbook *spec* describes."""
    payload: dict[str, Any] = {
        "name": spec["runbookName"],
        "steps": desired_steps(spec),
        "public": bool(spec.get("public", False)),
        "disable_ramdisk": bool(spec.get("disableRamdisk", False)),
        "extra": desired_extra(spec),
        "owner": str(spec["owner"]) if spec.get("owner") else None,
    }
    if spec.get("description"):
        payload["description"] = str(spec["description"])
    return payload


# ---------------------------------------------------------------------------
# The runbook
# ---------------------------------------------------------------------------


def _patch_operations(
    existing: dict[str, Any], spec: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return the JSON patch that converges *existing* onto *spec*."""
    operations: list[dict[str, Any]] = []

    def set_field(field: str, value: Any) -> None:
        operations.append({"op": "add", "path": f"/{field}", "value": value})

    steps = desired_steps(spec)
    if canonical_steps(existing.get("steps")) != canonical_steps(steps):
        set_field("steps", steps)

    extra = desired_extra(spec)
    if runbook_extra(existing) != extra:
        set_field("extra", extra)

    public = bool(spec.get("public", False))
    if bool(existing.get("public", False)) != public:
        set_field("public", public)

    disable_ramdisk = bool(spec.get("disableRamdisk", False))
    if bool(existing.get("disable_ramdisk", False)) != disable_ramdisk:
        set_field("disable_ramdisk", disable_ramdisk)

    description = str(spec.get("description") or "")
    if str(existing.get("description") or "") != description:
        set_field("description", description)

    if spec.get("owner"):
        owner = str(spec["owner"])
        if str(existing.get("owner") or "") != owner:
            set_field("owner", owner)
    elif not public and existing.get("owner") is not None:
        set_field("owner", None)

    return operations


def _runbook_uuid(runbook: dict[str, Any], name: str) -> str:
    """Return the UUID Ironic assigned to *runbook*.

    Every write goes to the UUID rather than the name. Ironic accepts either in
    the path, but the UUID is what the runbook keeps across a rename, so a
    write can never land on whatever else answers to that name.
    """
    uuid = str(runbook.get("uuid") or "")
    if not uuid:
        raise ConfigError(
            f"Ironic returned runbook {name!r} without a uuid, so it cannot be "
            "updated; the response was truncated or the API is not serving "
            "runbooks as expected"
        )
    return uuid


def ensure_runbook(conn: Any, spec: dict[str, Any]) -> dict[str, Any]:
    """Create or converge the runbook *spec* describes, and return it."""
    name = str(spec["runbookName"])
    existing = client.get_runbook(conn, name)

    if existing is None:
        payload = build_payload(spec)
        LOG.info(
            "Creating Ironic runbook %s with %s step(s)", name, len(payload["steps"])
        )
        return client.create_runbook(conn, payload)

    if is_managed_runbook(existing):
        LOG.info("Ironic runbook %s already exists and is operator-owned", name)
    else:
        LOG.info(
            "Adopting existing Ironic runbook %s; the CR is an ownership claim "
            "for it, so the operator markers are being written to its extra",
            name,
        )

    operations = _patch_operations(existing, spec)
    if not operations:
        return existing

    LOG.info(
        "Updating Ironic runbook %s: %s",
        name,
        ", ".join(operation["path"] for operation in operations),
    )
    return client.patch_runbook(conn, _runbook_uuid(existing, name), operations)


# ---------------------------------------------------------------------------
# Traits
# ---------------------------------------------------------------------------


def reconcile_traits(
    conn: Any, runbook: dict[str, Any], spec: dict[str, Any]
) -> list[str]:
    """Converge the traits of *runbook* onto *spec*, and return the result."""
    name = str(spec["runbookName"])
    desired = desired_traits(spec)
    current = [str(trait) for trait in runbook.get("traits") or []]
    if sorted(current) == sorted(desired):
        return current

    LOG.info(
        "Setting traits on Ironic runbook %s: have=%s want=%s",
        name,
        sorted(current),
        sorted(desired),
    )
    client.set_traits(conn, _runbook_uuid(runbook, name), desired)
    return desired


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def render_runbook(runbook: dict[str, Any]) -> dict[str, Any]:
    """Return the reconciled runbook as a loggable dict.

    Step arguments are summarised, not logged: they carry hardware settings and,
    for some interfaces, credentials.
    """
    steps = runbook.get("steps") if isinstance(runbook.get("steps"), list) else []
    return {
        "uuid": get_value(runbook, "uuid"),
        "name": get_value(runbook, "name"),
        "description": get_value(runbook, "description"),
        "public": get_value(runbook, "public"),
        "owner": get_value(runbook, "owner"),
        "disable_ramdisk": get_value(runbook, "disable_ramdisk"),
        "traits": sorted(str(trait) for trait in runbook.get("traits") or []),
        "steps": [
            f"{step.get('order')}:{step.get('interface')}.{step.get('step')}"
            for step in steps
            if isinstance(step, dict)
        ],
        "extra_keys": sorted(runbook_extra(runbook)),
    }


def sync_runbook(conn: Any, spec: dict[str, Any], _cache: Any = None) -> list[str]:
    """Converge one IronicRunbook spec."""
    name = validate_spec(spec)

    LOG.info("Reconciling Ironic runbook %s", name)
    runbook = ensure_runbook(conn, spec)
    traits = reconcile_traits(conn, runbook, spec)

    LOG.info(
        "Reconciled Ironic runbook: %s",
        # The traits the PUT just set are not in the body it answered with.
        json.dumps(render_runbook({**runbook, "traits": traits}), sort_keys=True),
    )
    return []
