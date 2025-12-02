import pytest

from ironic_understack.inspected_port import InspectedPort
from ironic_understack.vlan_group_name_convention import TopologyError
from ironic_understack.vlan_group_name_convention import vlan_group_names

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


def port(switch: str):
    return InspectedPort(
        mac_address="",
        name="",
        switch_system_name=switch,
        switch_chassis_id="",
        switch_port_id="",
    )


def test_vlan_group_name_single_cab():
    assert vlan_group_names(
        [
            port("a1-1-1.abc1"),
            port("a1-1-2.abc1"),
            port("a1-1-1f.abc1"),
            port("a1-1-2f.abc1"),
        ],
        mapping,
    ) == {
        "a1-1-1.abc1": "a1-1-network",
        "a1-1-2.abc1": "a1-1-network",
        "a1-1-1f.abc1": "a1-1-storage",
        "a1-1-2f.abc1": "a1-1-storage",
    }


def test_vlan_group_name_pair_cab():
    assert vlan_group_names(
        [
            port("a1-1-1.abc1"),
            port("a1-2-1.abc1"),
            port("a1-1-1f.abc1"),
            port("a1-2-1f.abc1"),
        ],
        mapping,
    ) == {
        "a1-1-1.abc1": "a1-1/a1-2-network",
        "a1-2-1.abc1": "a1-1/a1-2-network",
        "a1-1-1f.abc1": "a1-1/a1-2-storage",
        "a1-2-1f.abc1": "a1-1/a1-2-storage",
    }


def test_vlan_group_name_with_domain():
    assert vlan_group_names(
        [
            port("a1-1-1.abc1.domain"),
            port("a1-1-2.abc1.domain"),
            port("a1-1-1f.abc1.domain"),
            port("a1-1-2f.abc1.domain"),
        ],
        mapping,
    ) == {
        "a1-1-1.abc1.domain": "a1-1-network",
        "a1-1-2.abc1.domain": "a1-1-network",
        "a1-1-1f.abc1.domain": "a1-1-storage",
        "a1-1-2f.abc1.domain": "a1-1-storage",
    }


def test_vlan_group_name_invalid_format():
    with pytest.raises(ValueError, match="Unknown switch name format"):
        vlan_group_names([port("invalid.abc1")], mapping)

    with pytest.raises(ValueError, match="Unknown switch name format"):
        vlan_group_names([port(".abc1")], mapping)


def test_vlan_group_name_unknown_suffix():
    with pytest.raises(TopologyError, match="suffix a1-1-99.abc1 is not present"):
        vlan_group_names([port("a1-1-99.abc1")], mapping)

    with pytest.raises(TopologyError, match="suffix a1-1-5f.abc1 is not present"):
        vlan_group_names([port("a1-1-5f.abc1")], mapping)

    with pytest.raises(TopologyError, match="suffix a1-1-xyz.abc1 is not present"):
        vlan_group_names([port("a1-1-xyz.abc1")], mapping)


def test_vlan_group_name_many_dc():
    with pytest.raises(TopologyError, match="multiple"):
        vlan_group_names(
            [
                port("a1-1-1.abc1.domain"),
                port("a1-1-1.xyz2.domain"),
            ],
            mapping,
        )


def test_vlan_group_name_too_many_racks():
    with pytest.raises(TopologyError, match="more than two racks"):
        vlan_group_names(
            [
                port("a1-1-1.abc1.domain"),
                port("a1-2-1.abc1.domain"),
                port("a1-3-1.abc1.domain"),
            ],
            mapping,
        )


def test_vlan_group_name_too_many_switches():
    with pytest.raises(TopologyError, match="exactly two network switches"):
        vlan_group_names(
            [
                port("a1-1-1.abc1.domain"),
                port("a1-1-2.abc1.domain"),
                port("a1-1-3.abc1.domain"),
            ],
            mapping,
        )


def test_vlan_group_name_not_enough_switches():
    with pytest.raises(TopologyError, match="exactly two network switches"):
        vlan_group_names(
            [
                port("a1-1-1.abc1.domain"),
                port("a1-1-1.abc1.domain"),
            ],
            mapping,
        )
