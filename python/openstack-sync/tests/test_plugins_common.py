"""Tests for shared openstack-sync plugin utilities."""

from __future__ import annotations

from unittest import mock

import pytest
from openstack import exceptions as sdk_exceptions
from openstack.network.v2 import flavor as sdk_flavor
from openstack.network.v2 import service_profile as sdk_service_profile

from openstack_sync.plugins import common


def test_env_bool_accepts_only_lowercase_true_false(monkeypatch):
    assert common.env_bool("OPENSTACK_SYNC_TEST_MISSING_TRUE", True) is True
    assert common.env_bool("OPENSTACK_SYNC_TEST_MISSING_FALSE", False) is False

    monkeypatch.setenv("OPENSTACK_SYNC_TEST_BOOL", "true")
    assert common.env_bool("OPENSTACK_SYNC_TEST_BOOL", False) is True

    monkeypatch.setenv("OPENSTACK_SYNC_TEST_BOOL", "false")
    assert common.env_bool("OPENSTACK_SYNC_TEST_BOOL", True) is False


@pytest.mark.parametrize(
    "value",
    ["1", "0", "yes", "no", "on", "off", "TRUE", "FALSE", " true "],
)
def test_env_bool_rejects_boolean_aliases(monkeypatch, value):
    monkeypatch.setenv("OPENSTACK_SYNC_TEST_BOOL", value)

    with pytest.raises(common.ConfigError, match="must be true or false"):
        common.env_bool("OPENSTACK_SYNC_TEST_BOOL", False)


def test_get_value_reads_openstacksdk_attribute_names():
    profile = sdk_service_profile.ServiceProfile(
        id="profile-id",
        driver="neutron_understack.l3_router.vrf.Vrf",
        metainfo={"vni_alloc": "auto"},
    )

    assert common.resource_id(profile) == "profile-id"
    assert common.get_value(profile, "driver") == "neutron_understack.l3_router.vrf.Vrf"
    assert common.get_value(profile, "meta_info") == {"vni_alloc": "auto"}


def test_get_value_reads_exact_dict_keys_only():
    assert common.get_value(
        {"meta_info": {"vni_alloc": "auto"}},
        "meta_info",
    ) == {"vni_alloc": "auto"}
    assert (
        common.get_value(
            {"metainfo": {"vni_alloc": "auto"}},
            "meta_info",
            default="missing",
        )
        == "missing"
    )


def test_openstacksdk_maps_wire_names_to_attribute_names():
    profile = sdk_service_profile.ServiceProfile(
        id="profile-id",
        metainfo={"vni_alloc": "auto"},
    )
    flavor = sdk_flavor.Flavor(
        id="flavor-id",
        service_profiles=["profile-id"],
    )

    assert common.get_value(profile, "meta_info") == {"vni_alloc": "auto"}
    assert common.service_profile_ids(flavor) == ["profile-id"]


def test_service_profile_ids_reads_openstacksdk_flavor():
    flavor = sdk_flavor.Flavor(
        id="flavor-id",
        service_profiles=["profile-1", "profile-2"],
    )

    assert common.service_profile_ids(flavor) == ["profile-1", "profile-2"]


def test_get_value_returns_default_for_missing_or_none_values():
    assert common.get_value({"name": None}, "name", default="fallback") == "fallback"
    assert (
        common.get_value({"name": "router-flavor"}, "missing", default="fallback")
        == "fallback"
    )


def test_sdk_not_found_and_conflict_are_independent():
    """reconcile.py and prune.py catch these in separate except clauses.

    If either became a subclass of the other, the first clause would swallow
    both and, for example, a 409 "still in use" would be logged as "already
    absent" while the resource stayed attached.
    """
    assert not issubclass(
        sdk_exceptions.ConflictException, sdk_exceptions.NotFoundException
    )
    assert not issubclass(
        sdk_exceptions.NotFoundException, sdk_exceptions.ConflictException
    )


def test_meta_info_payload_canonicalizes_json_strings():
    assert common.meta_info_payload('{"b": 2, "a": 1}') == '{"a":1,"b":2}'


def test_normalize_meta_info_leaves_non_json_strings_unchanged():
    assert common.normalize_meta_info("{'b': 2, 'a': 1}") == "{'b': 2, 'a': 1}"


# ---------------------------------------------------------------------------
# API readiness
# ---------------------------------------------------------------------------


def test_wait_for_openstack_api_returns_as_soon_as_the_probe_succeeds():
    probe = mock.Mock(side_effect=[RuntimeError("not yet"), None])

    with mock.patch.object(common.time, "sleep") as sleep:
        common.wait_for_openstack_api("Ironic", probe, retries=5, delay=1)

    assert probe.call_count == 2
    sleep.assert_called_once_with(1)


def test_wait_for_openstack_api_gives_up_after_retries():
    probe = mock.Mock(side_effect=RuntimeError("down"))

    with (
        mock.patch.object(common.time, "sleep"),
        pytest.raises(RuntimeError, match="Ironic API did not become ready after 3"),
    ):
        common.wait_for_openstack_api("Ironic", probe, retries=3, delay=0)

    assert probe.call_count == 3


def test_wait_for_openstack_api_does_not_retry_a_config_error():
    """A misconfigured or too-old API does not become ready by waiting."""
    probe = mock.Mock(side_effect=common.ConfigError("this cloud is too old"))

    with (
        mock.patch.object(common.time, "sleep") as sleep,
        pytest.raises(common.ConfigError),
    ):
        common.wait_for_openstack_api("Ironic", probe, retries=30, delay=10)

    assert probe.call_count == 1
    sleep.assert_not_called()


def test_wait_for_openstack_network_probes_neutron_flavors():
    conn = mock.MagicMock()

    common.wait_for_openstack_network(conn, retries=1, delay=0)

    conn.network.flavors.assert_called_once_with()


def test_paginated_collection_uses_the_last_item_marker_for_the_next_page():
    pages = [
        {"runbooks": [{"uuid": "runbook-1"}, {"uuid": "runbook-2"}]},
        {"runbooks": [{"uuid": "runbook-3"}]},
    ]
    params_seen = []

    def fetch(params):
        params_seen.append(dict(params))
        return pages.pop(0)

    assert common.paginated_collection(
        fetch,
        collection_key="runbooks",
        marker_key="uuid",
        page_limit=2,
    ) == [{"uuid": "runbook-1"}, {"uuid": "runbook-2"}, {"uuid": "runbook-3"}]
    assert params_seen == [
        {"limit": 2},
        {"limit": 2, "marker": "runbook-2"},
    ]
