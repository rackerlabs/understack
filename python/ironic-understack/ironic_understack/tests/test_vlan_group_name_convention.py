import pytest

from ironic_understack.vlan_group_name_convention import vlan_group_name


def test_vlan_group_name_valid_switches():
    assert vlan_group_name("a1-1-1") == "a1-1-network"
    assert vlan_group_name("a1-2-1") == "a1-2-network"
    assert vlan_group_name("b12-1") == "b12-network"
    assert vlan_group_name("a2-12-1") == "a2-12-network"
    assert vlan_group_name("a2-12-2") == "a2-12-network"
    assert vlan_group_name("a2-12-1f") == "a2-12-storage"
    assert vlan_group_name("a2-12-2f") == "a2-12-storage"
    assert vlan_group_name("a2-12-3f") == "a2-12-storage-appliance"
    assert vlan_group_name("a2-12-4f") == "a2-12-storage-appliance"
    assert vlan_group_name("a2-12-1d") == "a2-12-bmc"


def test_vlan_group_name_with_domain():
    assert vlan_group_name("a2-12-1.iad3.rackspace.net") == "a2-12-network"
    assert vlan_group_name("a2-12-1f.lon3.rackspace.net") == "a2-12-storage"


def test_vlan_group_name_case_insensitive():
    assert vlan_group_name("A2-12-1F") == "a2-12-storage"
    assert vlan_group_name("A2-12-1") == "a2-12-network"


def test_vlan_group_name_invalid_format():
    with pytest.raises(ValueError, match="Unknown switch name format"):
        vlan_group_name("invalid")

    with pytest.raises(ValueError, match="Unknown switch name format"):
        vlan_group_name("")


def test_vlan_group_name_unknown_suffix():
    with pytest.raises(ValueError, match="Unknown switch suffix"):
        vlan_group_name("a2-12-99")

    with pytest.raises(ValueError, match="Unknown switch suffix"):
        vlan_group_name("a2-12-5f")

    with pytest.raises(ValueError, match="Unknown switch suffix"):
        vlan_group_name("a2-12-xyz")
