"""Tests for Ironic runbook prune behaviour."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.ironic.runbooks import client
from openstack_sync.plugins.ironic.runbooks import markers
from openstack_sync.plugins.ironic.runbooks import prune
from openstack_sync.plugins.ironic.runbooks.config import RUNBOOK_MICROVERSION
from tests.test_ironic_runbooks_reconcile import FakeBaremetal
from tests.test_ironic_runbooks_reconcile import _conn


def _owned(name: str) -> dict[str, Any]:
    return {
        "uuid": f"{name}-uuid",
        "name": name,
        "steps": [],
        "extra": markers.managed_extra({"version": "1.0.0"}),
    }


def _unowned(name: str) -> dict[str, Any]:
    return {"uuid": f"{name}-uuid", "name": name, "steps": [], "extra": {}}


def _spec(name: str) -> dict[str, Any]:
    return {"runbookName": name, "steps": []}


def _prune(fake: FakeBaremetal, specs: list[dict[str, Any]], **kwargs: Any) -> None:
    prune.prune_removed_runbooks(_conn(fake), specs, **kwargs)


def test_owned_runbook_absent_from_the_desired_set_is_deleted():
    fake = FakeBaremetal([_owned("CUSTOM_KEEP"), _owned("CUSTOM_GONE")])

    _prune(fake, [_spec("CUSTOM_KEEP")])

    assert sorted(fake.runbooks) == ["CUSTOM_KEEP"]
    assert fake.calls_for("DELETE") == ["/runbooks/CUSTOM_GONE-uuid"]


def test_owned_runbook_on_the_second_page_is_deleted():
    fake = FakeBaremetal([_owned("CUSTOM_KEEP"), _owned("CUSTOM_GONE")])

    with mock.patch.object(client, "_RUNBOOK_PAGE_LIMIT", 1):
        _prune(fake, [_spec("CUSTOM_KEEP")])

    assert sorted(fake.runbooks) == ["CUSTOM_KEEP"]
    get_params = [
        params
        for (method, _), params in zip(fake.calls, fake.params, strict=True)
        if method == "GET"
    ]
    assert get_params == [
        {"detail": "true", "limit": 1},
        {"detail": "true", "limit": 1, "marker": "CUSTOM_KEEP-uuid"},
        {"detail": "true", "limit": 1, "marker": "CUSTOM_GONE-uuid"},
    ]
    assert fake.calls_for("DELETE") == ["/runbooks/CUSTOM_GONE-uuid"]


def test_runbook_the_operator_does_not_own_is_kept():
    """A hand-made runbook is not the operator's to delete."""
    fake = FakeBaremetal([_unowned("CUSTOM_HANDMADE")])

    _prune(fake, [_spec("CUSTOM_KEEP")])

    assert sorted(fake.runbooks) == ["CUSTOM_HANDMADE"]
    assert fake.calls_for("DELETE") == []


def test_runbook_without_a_name_is_skipped():
    fake = FakeBaremetal()
    fake.runbooks["unnamed"] = {"uuid": "u", "extra": markers.managed_extra({})}

    _prune(fake, [_spec("CUSTOM_KEEP")])

    assert fake.calls_for("DELETE") == []


def test_empty_desired_set_is_refused_unless_a_cr_was_deleted():
    """An unreadable snapshot must not read as "delete everything"."""
    fake = FakeBaremetal([_owned("CUSTOM_GONE")])

    _prune(fake, [])
    assert sorted(fake.runbooks) == ["CUSTOM_GONE"]
    assert fake.calls == []

    _prune(fake, [], authoritative_empty=True)
    assert fake.runbooks == {}


def test_a_runbook_deleted_out_of_band_is_not_an_error():
    fake = FakeBaremetal([_owned("CUSTOM_GONE")])

    def vanish(path: str, method: str, **kwargs: Any) -> Any:
        if method == "DELETE":
            fake.calls.append((method, path))
            fake.bodies.append(None)
            fake.microversions.append(RUNBOOK_MICROVERSION)
            raise openstack_exceptions.NotFoundException("already gone")
        return FakeBaremetal.request(fake, path, method, **kwargs)

    with mock.patch.object(fake, "request", side_effect=vanish):
        _prune(fake, [_spec("CUSTOM_KEEP")])

    assert fake.calls_for("DELETE") == ["/runbooks/CUSTOM_GONE-uuid"]


def test_a_conflict_leaves_the_runbook_in_place():
    fake = FakeBaremetal([_owned("CUSTOM_GONE")])

    def conflict(path: str, method: str, **kwargs: Any) -> Any:
        if method == "DELETE":
            raise openstack_exceptions.ConflictException("still in use")
        return FakeBaremetal.request(fake, path, method, **kwargs)

    with mock.patch.object(fake, "request", side_effect=conflict):
        _prune(fake, [_spec("CUSTOM_KEEP")])

    assert sorted(fake.runbooks) == ["CUSTOM_GONE"]


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def test_the_delete_is_addressed_to_the_uuid_not_the_name():
    """Prune chose this runbook from a list snapshot taken earlier.

    By the time the DELETE goes out the name may belong to a runbook another CR
    has just created or adopted. The UUID from the snapshot cannot be reassigned
    that way, so it is what the delete addresses.
    """
    fake = FakeBaremetal([_owned("CUSTOM_GONE")])
    uuid = fake.uuid_of("CUSTOM_GONE")

    _prune(fake, [_spec("CUSTOM_KEEP")])

    assert fake.calls_for("DELETE") == [f"/runbooks/{uuid}"]
    assert fake.runbooks == {}


def test_a_runbook_with_no_uuid_fails_the_prune_instead_of_deleting():
    """Better a failed prune than a DELETE to /runbooks/None."""
    book = _owned("CUSTOM_GONE")
    del book["uuid"]
    fake = FakeBaremetal([book])

    with pytest.raises(ConfigError, match="without a uuid"):
        _prune(fake, [_spec("CUSTOM_KEEP")])

    assert fake.calls_for("DELETE") == []


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


def test_a_failure_other_than_conflict_or_not_found_stops_the_prune():
    """The framework reports a failed prune as a non-zero exit."""
    fake = FakeBaremetal([_owned("CUSTOM_GONE")])

    def forbidden(path: str, method: str, **kwargs: Any) -> Any:
        if method == "DELETE":
            raise openstack_exceptions.ForbiddenException("not allowed")
        return FakeBaremetal.request(fake, path, method, **kwargs)

    with (
        mock.patch.object(fake, "request", side_effect=forbidden),
        pytest.raises(openstack_exceptions.ForbiddenException),
    ):
        _prune(fake, [_spec("CUSTOM_KEEP")])
