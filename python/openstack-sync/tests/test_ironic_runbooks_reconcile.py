"""Tests for Ironic runbook reconciliation."""

from __future__ import annotations

import json
import types
from typing import Any
from unittest import mock

import pytest
import requests
from openstack import exceptions as openstack_exceptions

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.ironic.runbooks import client
from openstack_sync.plugins.ironic.runbooks import markers
from openstack_sync.plugins.ironic.runbooks import reconcile
from openstack_sync.plugins.ironic.runbooks.config import RUNBOOK_MICROVERSION

_NAME = "bmc-maintenance"


# ---------------------------------------------------------------------------
# Fake Ironic
# ---------------------------------------------------------------------------


def _response(status_code: int, body: Any = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.reason = "fake"
    if body is not None:
        response.headers["content-type"] = "application/json"
        response._content = json.dumps(body).encode("utf-8")
    else:
        response._content = b""
    return response


class FakeBaremetal:
    """In-memory stand-in for Ironic's runbook endpoints."""

    def __init__(self, runbooks: list[dict[str, Any]] | None = None) -> None:
        self.runbooks = {book["name"]: dict(book) for book in runbooks or []}
        self.calls: list[tuple[str, str]] = []
        self.bodies: list[Any] = []
        self.params: list[dict[str, Any] | None] = []
        self.microversions: list[str] = []

    # -- helpers for assertions ---------------------------------------------

    def calls_for(self, method: str) -> list[str]:
        return [path for call_method, path in self.calls if call_method == method]

    def _bodies_for(self, method: str) -> list[Any]:
        return [
            body
            for (call_method, _), body in zip(self.calls, self.bodies, strict=True)
            if call_method == method
        ]

    @property
    def patches(self) -> list[Any]:
        return self._bodies_for("PATCH")

    @property
    def trait_writes(self) -> list[Any]:
        return self._bodies_for("PUT")

    @property
    def created(self) -> Any:
        posted = self._bodies_for("POST")
        return posted[0] if posted else None

    def traits_of(self, name: str) -> list[str]:
        return list(self.runbooks[name].get("traits") or [])

    def uuid_of(self, name: str) -> str:
        """The UUID Ironic holds for *name*; writes must be addressed to it."""
        return str(self.runbooks[name]["uuid"])

    def _lookup(self, ident: str) -> dict[str, Any] | None:
        """Resolve *ident* the way Ironic does: as a UUID first, then a name."""
        for book in self.runbooks.values():
            if book.get("uuid") == ident:
                return book
        return self.runbooks.get(ident)

    # -- the API ------------------------------------------------------------

    def request(
        self,
        path: str,
        method: str,
        microversion: str | None = None,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> requests.Response:
        self.calls.append((method, path))
        self.bodies.append(json)
        self.params.append(params)
        self.microversions.append(str(microversion))

        parts = path.strip("/").split("/")
        if parts[0] != "runbooks":
            return _response(404, {"error_message": f"no route {path}"})

        if len(parts) == 1:
            if method == "GET":
                runbooks = list(self.runbooks.values())
                if params and "marker" in params:
                    marker = str(params["marker"])
                    start = next(
                        index + 1
                        for index, runbook in enumerate(runbooks)
                        if runbook["uuid"] == marker
                    )
                    runbooks = runbooks[start:]
                if params and "limit" in params:
                    runbooks = runbooks[: int(params["limit"])]
                return _response(200, {"runbooks": runbooks})
            if method == "POST":
                book = dict(json)
                if "traits" in book:
                    return _response(400, {"error_message": "traits not allowed"})
                book["traits"] = []
                # Ironic generates the UUID on create and returns it, which is
                # what the caller then addresses its traits PUT to.
                book.setdefault("uuid", f"{book['name']}-uuid")
                self.runbooks[book["name"]] = book
                return _response(201, book)

        if len(parts) == 2:
            ident = parts[1]
            book = self._lookup(ident)
            if book is None:
                return _response(404, {"error_message": f"no runbook {ident}"})
            if method == "GET":
                return _response(200, book)
            if method == "PATCH":
                for operation in json:
                    field = operation["path"].lstrip("/")
                    if field == "traits":
                        return _response(400, {"error_message": "traits not patchable"})
                    book[field] = operation["value"]
                    if field == "public" and operation["value"] is True:
                        book["owner"] = None
                return _response(200, book)
            if method == "DELETE":
                del self.runbooks[book["name"]]
                return _response(204)

        if len(parts) == 3 and parts[2] == "traits":
            ident = parts[1]
            book = self._lookup(ident)
            if book is None:
                return _response(404, {"error_message": f"no runbook {ident}"})
            if method == "PUT":
                book["traits"] = list((json or {}).get("traits") or [])
                return _response(204)

        return _response(405, {"error_message": f"{method} {path} not allowed"})


def _conn(fake: FakeBaremetal) -> Any:
    return types.SimpleNamespace(baremetal=fake)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _spec(**overrides: Any) -> dict[str, Any]:
    """A CR spec as the API server materialises it, with defaults applied."""
    spec: dict[str, Any] = {
        "runbookName": _NAME,
        "description": "Performs BMC maintenance",
        "public": True,
        "disableRamdisk": True,
        "traits": ["CUSTOM_DELL_IDRAC"],
        "steps": [
            {"interface": "management", "step": "clear_job_queue", "order": 1},
            {"interface": "management", "step": "set_bmc_clock", "order": 2},
        ],
        "extra": {"version": "1.0.0"},
    }
    spec.update(overrides)
    return spec


def _runbook(**overrides: Any) -> dict[str, Any]:
    """An Ironic runbook that matches ``_spec()`` exactly."""
    book: dict[str, Any] = {
        "uuid": "runbook-uuid",
        "name": _NAME,
        "description": "Performs BMC maintenance",
        "public": True,
        "owner": None,
        "disable_ramdisk": True,
        "traits": ["CUSTOM_DELL_IDRAC"],
        "steps": [
            {
                "interface": "management",
                "step": "clear_job_queue",
                "args": {},
                "order": 1,
            },
            {
                "interface": "management",
                "step": "set_bmc_clock",
                "args": {},
                "order": 2,
            },
        ],
        "extra": markers.managed_extra({"version": "1.0.0"}),
    }
    book.update(overrides)
    return book


# ---------------------------------------------------------------------------
# Spec validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["bmc-maintenance", "CUSTOM_BMC_MAINTENANCE", "firmware.r740xd_2.23~0"]
)
def test_any_url_safe_runbook_name_is_accepted(name: str):
    """A runbook name is a logical name; eligibility comes from spec.traits."""
    assert reconcile.validate_spec(_spec(runbookName=name)) == name


@pytest.mark.parametrize("name", ["", None])
def test_a_runbook_without_a_name_fails_the_cr(name: Any):
    with pytest.raises(ConfigError, match="spec.runbookName must be set"):
        reconcile.validate_spec(_spec(runbookName=name))


def test_a_public_runbook_may_not_also_have_an_owner():
    """Ironic's runbook PATCH refuses an owner on a public runbook.

    Such a CR would create once and fail on every update after that, so it is
    refused up front where the message can name the CR fields.
    """
    fake = FakeBaremetal()

    with pytest.raises(ConfigError, match="both public and owner"):
        reconcile.sync_runbook(_conn(fake), _spec(owner="project-123"))

    assert fake.calls == []


def test_an_owned_private_runbook_is_fine():
    assert reconcile.validate_spec(_spec(public=False, owner="project-123")) == _NAME


# ---------------------------------------------------------------------------
# Spec -> payload
# ---------------------------------------------------------------------------


def test_steps_always_carry_args():
    """Ironic stores step args NOT NULL with no default."""
    steps = reconcile.desired_steps(_spec())

    assert [step["args"] for step in steps] == [{}, {}]
    assert steps[0] == {
        "interface": "management",
        "step": "clear_job_queue",
        "args": {},
        "order": 1,
    }


def test_steps_keep_supplied_args_and_coerce_order():
    steps = reconcile.desired_steps(
        _spec(
            steps=[
                {
                    "interface": "bios",
                    "step": "apply_configuration",
                    "order": "3",
                    "args": {"settings": [{"name": "LogicalProc"}]},
                }
            ]
        )
    )

    assert steps == [
        {
            "interface": "bios",
            "step": "apply_configuration",
            "args": {"settings": [{"name": "LogicalProc"}]},
            "order": 3,
        }
    ]


@pytest.mark.parametrize(
    ("steps", "match"),
    [
        ([], "non-empty list"),
        (None, "non-empty list"),
        (["not-an-object"], "must be an object"),
        ([{"interface": "bios", "order": 1}], "missing required field"),
        ([{"interface": "bios", "step": "x", "order": "later"}], "must be an integer"),
    ],
)
def test_step_problems_fail_the_cr_by_name(steps: Any, match: str):
    with pytest.raises(ConfigError, match=match):
        reconcile.desired_steps(_spec(steps=steps))


def test_payload_sets_owner_null_when_the_spec_does_not_claim_one():
    payload = reconcile.build_payload(_spec())

    assert payload["owner"] is None
    assert payload["public"] is True
    assert payload["disable_ramdisk"] is True
    assert payload["description"] == "Performs BMC maintenance"
    assert payload["extra"] == markers.managed_extra({"version": "1.0.0"})


def test_payload_carries_the_owner_the_spec_claims():
    payload = reconcile.build_payload(_spec(public=False, owner="project-123"))

    assert payload["owner"] == "project-123"


def test_payload_never_sends_traits():
    """Ironic rejects traits in a create or patch body."""
    assert "traits" not in reconcile.build_payload(_spec())


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_when_the_runbook_is_absent():
    fake = FakeBaremetal()

    assert reconcile.sync_runbook(_conn(fake), _spec()) == []

    assert fake.calls_for("POST") == ["/runbooks"]
    assert fake.created["name"] == _NAME
    assert fake.created["extra"][markers.MANAGED_EXTRA_KEY] == (
        markers.MANAGED_EXTRA_VALUE
    )
    assert fake.microversions == [RUNBOOK_MICROVERSION] * len(fake.calls)


def test_create_sets_traits_through_the_sub_resource():
    fake = FakeBaremetal()

    reconcile.sync_runbook(_conn(fake), _spec())

    assert fake.calls_for("PUT") == [f"/runbooks/{fake.uuid_of(_NAME)}/traits"]
    assert fake.trait_writes == [{"traits": ["CUSTOM_DELL_IDRAC"]}]
    assert fake.traits_of(_NAME) == ["CUSTOM_DELL_IDRAC"]


def test_create_without_traits_writes_none():
    fake = FakeBaremetal()

    reconcile.sync_runbook(_conn(fake), _spec(traits=[]))

    assert fake.calls_for("PUT") == []


# ---------------------------------------------------------------------------
# Converged
# ---------------------------------------------------------------------------


def test_converged_runbook_is_not_written_to_at_all():
    """A needless PATCH is a Modified event the hook watches, so it requeues."""
    fake = FakeBaremetal([_runbook()])

    assert reconcile.sync_runbook(_conn(fake), _spec()) == []
    assert fake.calls == [("GET", f"/runbooks/{_NAME}")]


def test_step_order_from_ironic_does_not_count_as_drift():
    """Ironic does not promise to return steps in the order they were sent."""
    book = _runbook()
    book["steps"] = list(reversed(book["steps"]))
    fake = FakeBaremetal([book])

    reconcile.sync_runbook(_conn(fake), _spec())

    assert fake.patches == []


def test_trait_order_from_ironic_does_not_count_as_drift():
    fake = FakeBaremetal([_runbook(traits=["CUSTOM_B", "CUSTOM_A"])])

    reconcile.sync_runbook(_conn(fake), _spec(traits=["CUSTOM_A", "CUSTOM_B"]))

    assert fake.calls_for("PUT") == []


# ---------------------------------------------------------------------------
# Drift
# ---------------------------------------------------------------------------


def test_a_runbook_with_no_steps_at_all_is_patched_back():
    """Ironic omits ``steps`` from a fields-limited response; treat it as empty."""
    book = _runbook()
    del book["steps"]
    fake = FakeBaremetal([book])

    reconcile.sync_runbook(_conn(fake), _spec())

    (patch,) = fake.patches
    assert patch[0]["path"] == "/steps"


def test_step_drift_is_patched():
    book = _runbook()
    book["steps"] = book["steps"][:1]
    fake = FakeBaremetal([book])

    reconcile.sync_runbook(_conn(fake), _spec())

    (patch,) = fake.patches
    assert patch == [
        {"op": "add", "path": "/steps", "value": reconcile.desired_steps(_spec())}
    ]


def test_extra_drift_is_patched_with_the_markers_intact():
    fake = FakeBaremetal([_runbook(extra=markers.managed_extra({"version": "0.9.0"}))])

    reconcile.sync_runbook(_conn(fake), _spec())

    (patch,) = fake.patches
    assert patch[0]["path"] == "/extra"
    assert patch[0]["value"] == markers.managed_extra({"version": "1.0.0"})


def test_unowned_runbook_is_adopted_by_stamping_its_extra():
    """The CR is an ownership claim; adoption is what makes prune safe later."""
    fake = FakeBaremetal([_runbook(extra={"version": "1.0.0"})])

    reconcile.sync_runbook(_conn(fake), _spec())

    (patch,) = fake.patches
    assert patch == [
        {
            "op": "add",
            "path": "/extra",
            "value": markers.managed_extra({"version": "1.0.0"}),
        }
    ]
    assert markers.is_managed_runbook(fake.runbooks[_NAME])


def test_public_drift_is_patched():
    fake = FakeBaremetal([_runbook(public=False)])

    reconcile.sync_runbook(_conn(fake), _spec())

    (patch,) = fake.patches
    assert patch == [{"op": "add", "path": "/public", "value": True}]


def test_disable_ramdisk_drift_is_patched():
    fake = FakeBaremetal([_runbook(disable_ramdisk=False)])

    assert reconcile.sync_runbook(_conn(fake), _spec()) == []

    (patch,) = fake.patches
    assert patch == [{"op": "add", "path": "/disable_ramdisk", "value": True}]
    assert fake.runbooks[_NAME]["disable_ramdisk"] is True


def test_description_drift_is_patched():
    fake = FakeBaremetal([_runbook(description="stale")])

    reconcile.sync_runbook(_conn(fake), _spec(description="fresh"))

    (patch,) = fake.patches
    assert patch == [{"op": "add", "path": "/description", "value": "fresh"}]


def test_a_dropped_description_is_cleared():
    fake = FakeBaremetal([_runbook()])
    spec = _spec()
    del spec["description"]

    reconcile.sync_runbook(_conn(fake), spec)

    (patch,) = fake.patches
    assert patch == [{"op": "add", "path": "/description", "value": ""}]


def test_owner_is_cleared_when_the_spec_drops_it():
    fake = FakeBaremetal([_runbook(public=False, owner="project-123")])
    private = _spec(public=False)

    reconcile.sync_runbook(_conn(fake), private)
    (patch,) = fake.patches
    assert patch == [{"op": "add", "path": "/owner", "value": None}]
    assert fake.runbooks[_NAME]["owner"] is None


def test_owner_is_patched_when_the_spec_claims_one():
    fake = FakeBaremetal([_runbook(public=False, owner="project-123")])
    private = _spec(public=False)

    reconcile.sync_runbook(_conn(fake), {**private, "owner": "project-456"})
    (patch,) = fake.patches
    assert patch == [{"op": "add", "path": "/owner", "value": "project-456"}]


def test_switching_to_public_clears_owner_through_ironic():
    fake = FakeBaremetal([_runbook(public=False, owner="project-123")])

    reconcile.sync_runbook(_conn(fake), _spec(public=True))

    (patch,) = fake.patches
    assert patch == [{"op": "add", "path": "/public", "value": True}]
    assert fake.runbooks[_NAME]["owner"] is None


def test_patch_uses_add_so_it_works_on_fields_ironic_omits():
    """``replace`` on a member Ironic does not return is rejected by the patch."""
    fake = FakeBaremetal([_runbook(public=False, description="stale")])

    reconcile.sync_runbook(_conn(fake), _spec())

    assert {operation["op"] for patch in fake.patches for operation in patch} == {"add"}


# ---------------------------------------------------------------------------
# Traits
# ---------------------------------------------------------------------------


def test_traits_are_replaced_in_one_request():
    """One PUT for the whole set, so no node sees a half-applied runbook."""
    fake = FakeBaremetal([_runbook(traits=["CUSTOM_STALE", "CUSTOM_DELL_IDRAC"])])

    reconcile.sync_runbook(
        _conn(fake), _spec(traits=["CUSTOM_DELL_IDRAC", "CUSTOM_NEW"])
    )

    assert fake.calls_for("PUT") == [f"/runbooks/{fake.uuid_of(_NAME)}/traits"]
    assert fake.trait_writes == [{"traits": ["CUSTOM_DELL_IDRAC", "CUSTOM_NEW"]}]
    assert fake.traits_of(_NAME) == ["CUSTOM_DELL_IDRAC", "CUSTOM_NEW"]


def test_dropping_every_trait_clears_them():
    fake = FakeBaremetal([_runbook()])

    reconcile.sync_runbook(_conn(fake), _spec(traits=[]))

    assert fake.trait_writes == [{"traits": []}]
    assert fake.traits_of(_NAME) == []


# ---------------------------------------------------------------------------
# Identifiers
# ---------------------------------------------------------------------------


def test_writes_are_addressed_to_the_uuid_not_the_name():
    """The CR supplies a name, so the read is by name and every write by UUID.

    Ironic resolves either identifier in the path, so a name-addressed write
    works right up until the name stops belonging to the runbook the operator
    read; the UUID it already holds has no such window.
    """
    fake = FakeBaremetal([_runbook(public=False, traits=["CUSTOM_STALE"])])

    reconcile.sync_runbook(_conn(fake), _spec())

    uuid = fake.uuid_of(_NAME)
    assert fake.calls_for("GET") == [f"/runbooks/{_NAME}"]
    assert fake.calls_for("PATCH") == [f"/runbooks/{uuid}"]
    assert fake.calls_for("PUT") == [f"/runbooks/{uuid}/traits"]


def test_a_runbook_with_no_uuid_fails_the_cr_instead_of_writing():
    """Better a failed CR than a PATCH to /runbooks/None."""
    book = _runbook(public=False)
    del book["uuid"]
    fake = FakeBaremetal([book])

    with pytest.raises(ConfigError, match="without a uuid"):
        reconcile.sync_runbook(_conn(fake), _spec())

    assert fake.calls_for("PATCH") == []


# ---------------------------------------------------------------------------
# Microversion
# ---------------------------------------------------------------------------


def _check(reported: str | None) -> None:
    with mock.patch.object(
        client.openstack_utils,
        "maximum_supported_microversion",
        return_value=reported,
    ):
        client.check_microversion(_conn(FakeBaremetal()))


def test_check_microversion_accepts_a_cloud_at_the_required_version():
    _check(RUNBOOK_MICROVERSION)


def test_check_microversion_rejects_a_cloud_that_is_too_old():
    with pytest.raises(ConfigError, match=f"requires {RUNBOOK_MICROVERSION}"):
        _check("1.101")


def test_check_microversion_rejects_an_undiscoverable_endpoint():
    with pytest.raises(ConfigError, match="Could not determine"):
        _check(None)


def test_check_microversion_rejects_a_version_it_cannot_compare():
    with pytest.raises(ConfigError, match="unusable API microversion"):
        _check("latest")


def test_readiness_probe_does_not_retry_a_cloud_that_cannot_be_fixed():
    """A too-old Ironic will not become new by waiting retries * delay seconds."""
    conn = _conn(FakeBaremetal())

    with (
        mock.patch.object(
            client.openstack_utils,
            "maximum_supported_microversion",
            return_value="1.101",
        ),
        mock.patch("openstack_sync.plugins.common.time.sleep") as sleep,
        pytest.raises(ConfigError),
    ):
        client.wait_for_runbook_api(conn, retries=5, delay=0)

    sleep.assert_not_called()


def test_readiness_probe_lists_runbooks_so_policy_failures_surface_early():
    fake = FakeBaremetal()

    with mock.patch.object(
        client.openstack_utils,
        "maximum_supported_microversion",
        return_value=RUNBOOK_MICROVERSION,
    ):
        client.wait_for_runbook_api(_conn(fake), retries=1, delay=0)

    assert fake.calls == [("GET", "/runbooks")]


# ---------------------------------------------------------------------------
# Client edges
# ---------------------------------------------------------------------------


def test_get_runbook_returns_none_for_an_absent_name():
    assert client.get_runbook(_conn(FakeBaremetal()), _NAME) is None


def test_client_raises_typed_errors_for_other_failures():
    fake = FakeBaremetal()
    # POST /runbooks/<name>/traits is not a route Ironic serves.
    with pytest.raises(openstack_exceptions.HttpException):
        client._request(_conn(fake), "POST", f"/runbooks/{_NAME}/traits")


def test_delete_runbook_treats_an_absent_runbook_as_done():
    client.delete_runbook(_conn(FakeBaremetal()), _NAME)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def test_render_runbook_summarises_steps_without_their_args():
    """Step args carry hardware settings and, for some interfaces, secrets."""
    rendered = reconcile.render_runbook(
        _runbook(
            steps=[{"interface": "bios", "step": "apply", "args": {"p": "s3cret"}}]
        )
    )

    assert rendered["steps"] == ["None:bios.apply"]
    assert "s3cret" not in json.dumps(rendered)
    assert rendered["traits"] == ["CUSTOM_DELL_IDRAC"]
    assert rendered["description"] == "Performs BMC maintenance"
    assert rendered["extra_keys"] == sorted(markers.managed_extra({"version": "1.0.0"}))
