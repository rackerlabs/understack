import pytest

from ironic_understack.vlan_group_name_convention import vlan_group_name

mapping = {
    "1": "network",
    "2": "network",
    "3": "network",
    "4": "network",
    "1f": "storage",
    "2f": "storage",
    "3f": "storage-appliance",
    "4f": "storage-appliance",
    "1d": "bmc",
}

def test_vlan_group_name_valid_switches():
    assert vlan_group_name("a1-1-1", mapping) == "a1-1-network"
    assert vlan_group_name("a1-2-1", mapping) == "a1-2-network"
    assert vlan_group_name("b12-1", mapping) == "b12-network"
    assert vlan_group_name("a2-12-1", mapping) == "a2-12-network"
    assert vlan_group_name("a2-12-2", mapping) == "a2-12-network"
    assert vlan_group_name("a2-12-1f", mapping) == "a2-12-storage"
    assert vlan_group_name("a2-12-2f", mapping) == "a2-12-storage"
    assert vlan_group_name("a2-12-3f", mapping) == "a2-12-storage-appliance"
    assert vlan_group_name("a2-12-4f", mapping) == "a2-12-storage-appliance"
    assert vlan_group_name("a2-12-1d", mapping) == "a2-12-bmc"


def test_vlan_group_name_with_domain():
    assert vlan_group_name("a2-12-1.iad3.rackspace.net", mapping) == "a2-12-network"
    assert vlan_group_name("a2-12-1f.lon3.rackspace.net", mapping) == "a2-12-storage"


def test_vlan_group_name_case_insensitive():
    assert vlan_group_name("A2-12-1F", mapping) == "a2-12-storage"
    assert vlan_group_name("A2-12-1", mapping) == "a2-12-network"


def test_vlan_group_name_invalid_format():
    with pytest.raises(ValueError, match="Unknown switch name format"):
        vlan_group_name("invalid", mapping)

    with pytest.raises(ValueError, match="Unknown switch name format"):
        vlan_group_name("", mapping)


def test_vlan_group_name_unknown_suffix():
    with pytest.raises(ValueError, match="Switch suffix 99 is not present"):
        vlan_group_name("a2-12-99", mapping)

    with pytest.raises(ValueError, match="Switch suffix 5f is not present"):
        vlan_group_name("a2-12-5f", mapping)

    with pytest.raises(ValueError, match="Switch suffix xyz is not present"):
        vlan_group_name("a2-12-xyz", mapping)
