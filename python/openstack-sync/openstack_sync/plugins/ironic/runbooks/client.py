"""Ironic runbook API calls through the baremetal proxy."""

from __future__ import annotations

import logging
from typing import Any

from openstack import exceptions as openstack_exceptions
from openstack import utils as openstack_utils

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.common import paginated_collection
from openstack_sync.plugins.common import wait_for_openstack_api
from openstack_sync.plugins.ironic.runbooks.config import RUNBOOK_MICROVERSION

LOG = logging.getLogger(__name__)

_RUNBOOKS_PATH = "/runbooks"
_RUNBOOK_PAGE_LIMIT = 100


# ---------------------------------------------------------------------------
# Readiness
# ---------------------------------------------------------------------------


def _version_tuple(microversion: str) -> tuple[int, ...]:
    """Return *microversion* as a comparable tuple of ints."""
    try:
        return tuple(int(part) for part in str(microversion).split("."))
    except ValueError as exc:
        raise ConfigError(
            f"Ironic reported an unusable API microversion {microversion!r}"
        ) from exc


def check_microversion(conn: Any) -> None:
    """Raise unless the cloud can serve :data:`RUNBOOK_MICROVERSION`."""
    supported = openstack_utils.maximum_supported_microversion(
        conn.baremetal, RUNBOOK_MICROVERSION
    )
    if supported is None:
        raise ConfigError(
            "Could not determine the Ironic API microversion; the baremetal "
            "endpoint did not report its supported versions, so the runbook "
            f"API cannot be used (requires {RUNBOOK_MICROVERSION})"
        )
    if _version_tuple(supported) < _version_tuple(RUNBOOK_MICROVERSION):
        raise ConfigError(
            f"Ironic supports API microversion {supported} but this hook "
            f"requires {RUNBOOK_MICROVERSION} for runbook descriptions and "
            "traits; upgrade Ironic or disable the ironicRunbooks hook"
        )


def wait_for_runbook_api(
    conn: Any,
    retries: int = 30,
    delay: float = 10.0,
) -> None:
    """Poll until the runbook API is reachable and listable."""

    def probe() -> None:
        check_microversion(conn)
        list_runbooks(conn, limit=1)

    wait_for_openstack_api("Ironic", probe, retries=retries, delay=delay)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


def _request(conn: Any, method: str, path: str, **kwargs: Any) -> Any:
    """Send one baremetal request and raise for any non-2xx response."""
    response = conn.baremetal.request(
        path, method, microversion=RUNBOOK_MICROVERSION, **kwargs
    )
    openstack_exceptions.raise_from_response(response)
    return response


def _json_body(response: Any) -> dict[str, Any]:
    """Return the JSON body of *response*, or an empty dict when it has none."""
    if not response.content:
        return {}
    body = response.json()
    return body if isinstance(body, dict) else {}


def list_runbooks(conn: Any, limit: int | None = None) -> list[dict[str, Any]]:
    """Return every runbook visible to these credentials, with all fields."""
    if limit is not None:
        response = _request(
            conn, "GET", _RUNBOOKS_PATH, params={"detail": "true", "limit": limit}
        )
        runbooks = _json_body(response).get("runbooks", [])
        return [runbook for runbook in runbooks if isinstance(runbook, dict)]

    def fetch_page(params: dict[str, Any]) -> dict[str, Any]:
        return _json_body(
            _request(
                conn,
                "GET",
                _RUNBOOKS_PATH,
                params={"detail": "true", **params},
            )
        )

    runbooks = paginated_collection(
        fetch_page,
        collection_key="runbooks",
        marker_key="uuid",
        page_limit=_RUNBOOK_PAGE_LIMIT,
    )
    return [runbook for runbook in runbooks if isinstance(runbook, dict)]


def get_runbook(conn: Any, name: str) -> dict[str, Any] | None:
    """Return the runbook named *name*, or None when Ironic does not have it."""
    try:
        response = _request(conn, "GET", f"{_RUNBOOKS_PATH}/{name}")
    except openstack_exceptions.NotFoundException:
        return None
    return _json_body(response)


def create_runbook(conn: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a runbook from *payload* and return it as Ironic stored it."""
    response = _request(conn, "POST", _RUNBOOKS_PATH, json=payload)
    return _json_body(response)


def patch_runbook(
    conn: Any, runbook_uuid: str, patch: list[dict[str, Any]]
) -> dict[str, Any]:
    """Apply a JSON patch to the runbook with UUID *runbook_uuid*.

    Writes address the runbook by UUID, not by name. Ironic resolves either in
    the path, but the UUID is the identifier that cannot be renamed out from
    under the request.
    """
    response = _request(conn, "PATCH", f"{_RUNBOOKS_PATH}/{runbook_uuid}", json=patch)
    return _json_body(response)


def delete_runbook(conn: Any, name: str) -> None:
    """Delete the runbook named *name*, treating an absent one as success."""
    try:
        _request(conn, "DELETE", f"{_RUNBOOKS_PATH}/{name}")
    except openstack_exceptions.NotFoundException:
        LOG.info("Runbook %s is already absent from Ironic", name)


def set_traits(conn: Any, runbook_uuid: str, traits: list[str]) -> None:
    """Replace every trait on the runbook with UUID *runbook_uuid*.

    Addressed by UUID for the same reason as :func:`patch_runbook`.
    """
    _request(
        conn,
        "PUT",
        f"{_RUNBOOKS_PATH}/{runbook_uuid}/traits",
        json={"traits": traits},
    )
