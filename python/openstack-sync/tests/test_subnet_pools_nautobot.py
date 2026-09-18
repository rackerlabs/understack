"""Tests for Nautobot resolution of NeutronSubnetPool CRs.

The CR is the source of truth for pool policy (name, address scope, prefix
lengths); Nautobot owns only the CIDRs. These tests cover CIDR extraction, IP
version inference, and the ``require`` guardrails each referenced prefix must
satisfy. Policy derivation from custom_fields no longer exists.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from openstack_sync.plugins.common import ConfigError
from openstack_sync.plugins.neutron.subnet_pools import nautobot

PUBLIC_ID = "2bc3ecab-b6dc-46cd-9bd4-1c0ea8a07f87"
PUBLIC_ID_2 = "53c8ee3b-09b9-41ab-a413-b1a1f5ecec6a"


def _spec(**overrides: Any) -> dict[str, Any]:
    """A CR carrying the full pool contract plus Nautobot prefix references."""
    spec: dict[str, Any] = {
        "name": "PUBLIC-IP-POOL",
        "address_scope": {"name": "publicnet-ip4"},
        "minimum_prefix_length": 27,
        "default_prefix_length": 28,
        "maximum_prefix_length": 30,
        "shared": True,
        "nautobot": {
            "url": "https://nautobot.example.test",
            "api_version": "2.0",
            "tokenSecretRef": {"secretName": "nautobot-token", "key": "token"},
            "prefix_refs": [{"id": PUBLIC_ID}, {"id": PUBLIC_ID_2}],
            "require": {
                "location": "iad3-dev",
                "tags": ["openstack-subnet-pool"],
                "status": "Active",
                "type": "pool",
                "namespace": "Rackspace",
            },
        },
    }
    spec.update(overrides)
    return spec


def _single_ref_spec(**overrides: Any) -> dict[str, Any]:
    """A CR referencing exactly one prefix, for single-record cases."""
    spec = _spec(**overrides)
    spec["nautobot"] = {**spec["nautobot"], "prefix_refs": [{"id": PUBLIC_ID}]}
    return spec


def _prefix(prefix: str, **overrides: Any) -> SimpleNamespace:
    # A Nautobot prefix serializes location as null; require.location is enforced
    # by the ?location= query filter, so the record carries no location field.
    defaults = {
        "id": "prefix-id",
        "prefix": prefix,
        "status": SimpleNamespace(name="Active"),
        "type": "pool",
        "namespace": SimpleNamespace(name="Rackspace"),
        "tags": [SimpleNamespace(name="openstack-subnet-pool")],
    }
    return SimpleNamespace(**{**defaults, **overrides})


def _client(*prefixes: SimpleNamespace) -> Any:
    client = mock.MagicMock()
    client.ipam.prefixes.get.side_effect = list(prefixes)
    return client


@pytest.fixture(autouse=True)
def _clear_site_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep a real UNDERSTACK_SITE out of the tests; each sets it explicitly."""
    monkeypatch.delenv(nautobot.SITE_ENV, raising=False)


def _resolve(monkeypatch, spec, *prefixes, cache=None):
    client = _client(*prefixes)
    monkeypatch.setattr(nautobot, "read_secret_key", mock.Mock(return_value="nb-token"))
    monkeypatch.setattr(nautobot.pynautobot, "api", mock.Mock(return_value=client))
    return nautobot.resolve_spec(spec, cache if cache is not None else {}, "openstack")


# ---------------------------------------------------------------------------
# CIDR extraction and IP version
# ---------------------------------------------------------------------------


def test_resolve_spec_attaches_cidrs_and_ip_version(monkeypatch):
    resolved = _resolve(
        monkeypatch,
        _spec(),
        _prefix("204.232.163.128/25", id=PUBLIC_ID),
        _prefix("10.4.88.0/24", id=PUBLIC_ID_2),
    )

    assert resolved["prefixes"] == ["204.232.163.128/25", "10.4.88.0/24"]
    assert resolved["ip_version"] == 4


def test_resolve_spec_leaves_policy_fields_untouched(monkeypatch):
    """Resolution must not read or alter the pool policy on the CR."""
    resolved = _resolve(
        monkeypatch,
        _spec(),
        _prefix("204.232.163.128/25", id=PUBLIC_ID),
        _prefix("10.4.88.0/24", id=PUBLIC_ID_2),
    )

    assert resolved["name"] == "PUBLIC-IP-POOL"
    assert resolved["address_scope"] == {"name": "publicnet-ip4"}
    assert resolved["minimum_prefix_length"] == 27
    assert resolved["default_prefix_length"] == 28
    assert resolved["maximum_prefix_length"] == 30


def test_resolve_spec_requires_name(monkeypatch):
    spec = _single_ref_spec()
    del spec["name"]
    with pytest.raises(ConfigError, match="name must be set"):
        _resolve(monkeypatch, spec, _prefix("10.0.0.0/24"))


def test_resolve_spec_rejects_mixed_ip_versions(monkeypatch):
    with pytest.raises(ConfigError, match="mixed IP versions"):
        _resolve(
            monkeypatch,
            _spec(),
            _prefix("10.0.0.0/24", id=PUBLIC_ID),
            _prefix("2001:db8::/64", id=PUBLIC_ID_2),
        )


# ---------------------------------------------------------------------------
# Location is enforced server-side via the ?location= filter
# ---------------------------------------------------------------------------


def test_resolve_spec_filters_lookup_by_require_location(monkeypatch):
    """require.location is passed to the prefix lookup as a query filter.

    A Nautobot prefix serializes location as null, so the association can only
    be matched by querying ?location=; the resolver must send it, not read a
    location field off the record.
    """
    client = _client(
        _prefix("204.232.163.128/25", id=PUBLIC_ID),
        _prefix("10.4.88.0/24", id=PUBLIC_ID_2),
    )
    monkeypatch.setattr(nautobot, "read_secret_key", mock.Mock(return_value="nb-token"))
    monkeypatch.setattr(nautobot.pynautobot, "api", mock.Mock(return_value=client))

    nautobot.resolve_spec(_spec(), {}, "openstack")

    for call in client.ipam.prefixes.get.call_args_list:
        assert call.kwargs["location"] == "iad3-dev"
        assert "id" in call.kwargs


def test_resolve_spec_rejects_prefix_not_under_required_location(monkeypatch):
    """A prefix not returned under the required location fails the guardrail.

    Nautobot returns nothing for ?id=<uuid>&location=<other>, which the resolver
    reports as the prefix not being under the required location.
    """
    with pytest.raises(ConfigError, match="was not found under location 'iad3-dev'"):
        _resolve(monkeypatch, _single_ref_spec(), None)


def _location_400_request_error() -> nautobot.pynautobot.RequestError:
    """Build the RequestError Nautobot raises for an invalid location choice.

    Nautobot answers ``?location=<bad>`` with HTTP 400 and a body naming the
    location field; pynautobot wraps the response in RequestError, exposing it
    as ``.req`` with ``.error`` holding the body text.
    """
    response = SimpleNamespace(
        status_code=400,
        reason="Bad Request",
        url="https://nautobot.example.test/api/ipam/prefixes/",
        text='{"location": ["Select a valid choice. iad is not one of the '
        'available choices."]}',
        request=SimpleNamespace(body=None),
    )
    response.json = lambda: {"location": ["Select a valid choice."]}
    return nautobot.pynautobot.RequestError(response)


def test_resolve_spec_reports_invalid_location_choice(monkeypatch):
    """A wrong-level or typo'd location fails as a guardrail misconfig, not a 500.

    Location is a hierarchical choice filter, so Nautobot rejects a Region name
    like 'iad' (instead of the Site 'iad3-dev') with HTTP 400. The resolver must
    translate that into a message pointing at spec.nautobot.require.location.
    """
    client = mock.MagicMock()
    client.ipam.prefixes.get.side_effect = _location_400_request_error()
    monkeypatch.setattr(nautobot, "read_secret_key", mock.Mock(return_value="nb-token"))
    monkeypatch.setattr(nautobot.pynautobot, "api", mock.Mock(return_value=client))

    spec = _single_ref_spec()
    spec["nautobot"] = {**spec["nautobot"], "require": {"location": "iad"}}
    with pytest.raises(ConfigError, match="is not a valid Nautobot location"):
        nautobot.resolve_spec(spec, {}, "openstack")


def test_resolve_spec_omits_location_filter_when_not_required(monkeypatch):
    """With no require.location, the lookup is by id only."""
    spec = _single_ref_spec()
    spec["nautobot"] = {**spec["nautobot"], "require": {}}
    client = _client(_prefix("10.0.0.0/24", id=PUBLIC_ID))
    monkeypatch.setattr(nautobot, "read_secret_key", mock.Mock(return_value="nb-token"))
    monkeypatch.setattr(nautobot.pynautobot, "api", mock.Mock(return_value=client))

    nautobot.resolve_spec(spec, {}, "openstack")

    (call,) = client.ipam.prefixes.get.call_args_list
    assert "location" not in call.kwargs


def test_resolve_spec_defaults_location_from_site_env(monkeypatch):
    """With no require.location, the lookup falls back to UNDERSTACK_SITE."""
    monkeypatch.setenv(nautobot.SITE_ENV, "iad3-dev")
    spec = _single_ref_spec()
    spec["nautobot"] = {**spec["nautobot"], "require": {}}
    client = _client(_prefix("10.0.0.0/24", id=PUBLIC_ID))
    monkeypatch.setattr(nautobot, "read_secret_key", mock.Mock(return_value="nb-token"))
    monkeypatch.setattr(nautobot.pynautobot, "api", mock.Mock(return_value=client))

    nautobot.resolve_spec(spec, {}, "openstack")

    (call,) = client.ipam.prefixes.get.call_args_list
    assert call.kwargs["location"] == "iad3-dev"


def test_resolve_spec_require_location_overrides_site_env(monkeypatch):
    """An explicit require.location wins over UNDERSTACK_SITE."""
    monkeypatch.setenv(nautobot.SITE_ENV, "other-site")
    client = _client(_prefix("10.0.0.0/24", id=PUBLIC_ID))
    monkeypatch.setattr(nautobot, "read_secret_key", mock.Mock(return_value="nb-token"))
    monkeypatch.setattr(nautobot.pynautobot, "api", mock.Mock(return_value=client))

    nautobot.resolve_spec(_single_ref_spec(), {}, "openstack")

    (call,) = client.ipam.prefixes.get.call_args_list
    assert call.kwargs["location"] == "iad3-dev"


# ---------------------------------------------------------------------------
# Loading and guardrails
# ---------------------------------------------------------------------------


def test_resolve_spec_reuses_cached_client(monkeypatch):
    client = _client(
        _prefix("204.232.163.128/25", id=PUBLIC_ID),
        _prefix("10.4.88.0/24", id=PUBLIC_ID_2),
        _prefix("204.232.163.128/25", id=PUBLIC_ID),
        _prefix("10.4.88.0/24", id=PUBLIC_ID_2),
    )
    api = mock.Mock(return_value=client)
    monkeypatch.setattr(nautobot, "read_secret_key", mock.Mock(return_value="nb-token"))
    monkeypatch.setattr(nautobot.pynautobot, "api", api)
    cache: dict[str, Any] = {}

    nautobot.resolve_spec(_spec(), cache, "openstack")
    nautobot.resolve_spec(_spec(), cache, "openstack")

    api.assert_called_once()


def test_resolve_spec_rejects_missing_prefix(monkeypatch):
    with pytest.raises(ConfigError, match="was not found"):
        _resolve(monkeypatch, _spec(), None)


def test_resolve_spec_rejects_prefix_that_fails_requirements(monkeypatch):
    with pytest.raises(ConfigError, match="status is 'Reserved'"):
        _resolve(
            monkeypatch,
            _spec(),
            _prefix("204.232.163.128/25", id=PUBLIC_ID),
            _prefix(
                "10.4.88.0/24",
                id=PUBLIC_ID_2,
                status=SimpleNamespace(name="Reserved"),
            ),
        )


def test_resolve_spec_rejects_prefix_missing_required_tag(monkeypatch):
    with pytest.raises(ConfigError, match="missing tags"):
        _resolve(
            monkeypatch,
            _single_ref_spec(),
            _prefix("10.0.0.0/24", tags=[]),
        )


# ---------------------------------------------------------------------------
# Field extraction across the real pynautobot Record shapes (see live data)
# ---------------------------------------------------------------------------


class _ChoiceRecord:
    """Mimics a pynautobot choice field: {value, label}, no name."""

    def __init__(self, value: str, label: str) -> None:
        self.value = value
        self.label = label
        self.name = None

    def __str__(self) -> str:  # pynautobot uses display/name/label
        return self.label


class _DisplayRecord:
    """Mimics a pynautobot tag/status Record whose text is only via str()."""

    def __init__(self, display: str) -> None:
        self._display = display
        self.name = None
        self.value = None

    def __str__(self) -> str:
        return self._display


def test_field_text_reads_choice_value_not_label():
    """Type comes back as {value: 'pool', label: 'Pool'}; match the value."""
    assert nautobot._field_text(_ChoiceRecord("pool", "Pool")) == "pool"


def test_field_text_falls_back_to_str_for_display_only_records():
    """Tags expose their value only through str(); _field_text must use it."""
    assert nautobot._field_text(_DisplayRecord("openstack-subnet-pool")) == (
        "openstack-subnet-pool"
    )


def test_resolve_spec_accepts_choice_type_and_display_tags(monkeypatch):
    """End-to-end guardrails pass against the live Record shapes.

    Reproduces the shapes the live query returns: type as a value/label choice,
    tags whose value is only reachable via str(). Regression for the guardrails
    reporting spurious 'type is None' / 'missing tags' failures.
    """
    prefix = _prefix(
        "10.0.0.0/24",
        id=PUBLIC_ID,
        type=_ChoiceRecord("pool", "Pool"),
        tags=[_DisplayRecord("openstack-subnet-pool")],
    )
    resolved = _resolve(monkeypatch, _single_ref_spec(), prefix)
    assert resolved["prefixes"] == ["10.0.0.0/24"]


def test_prefix_refs_require_id():
    with pytest.raises(ConfigError, match="prefix_refs\\[0\\].id"):
        nautobot._nautobot_prefix_refs({"nautobot": {"prefix_refs": [{}]}})


def test_prefix_refs_must_be_non_empty():
    with pytest.raises(ConfigError, match="prefix_refs must be a non-empty list"):
        nautobot._nautobot_prefix_refs({"nautobot": {"prefix_refs": []}})
