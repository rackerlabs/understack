"""Tests for shared openstack-sync plugin utilities."""

from __future__ import annotations

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


def test_service_profile_ids_requires_list():
    with pytest.raises(TypeError, match="service_profile_ids"):
        common.service_profile_ids({"service_profile_ids": "profile-id"})


def test_sdk_exception_classifiers_match_openstacksdk_classes():
    assert common.is_not_found(sdk_exceptions.NotFoundException("missing"))
    assert not common.is_not_found(sdk_exceptions.ConflictException("conflict"))

    assert common.is_conflict(sdk_exceptions.ConflictException("conflict"))
    assert not common.is_conflict(sdk_exceptions.NotFoundException("missing"))


def test_meta_info_payload_canonicalizes_json_strings():
    assert common.meta_info_payload('{"b": 2, "a": 1}') == '{"a":1,"b":2}'


def test_normalize_meta_info_leaves_non_json_strings_unchanged():
    assert common.normalize_meta_info("{'b': 2, 'a': 1}") == "{'b': 2, 'a': 1}"
