from collections.abc import Iterable

from ironic_understack.inspected_port import InspectedPort


class TopologyError(Exception):
    pass


def vlan_group_names(
    ports: list[InspectedPort], mapping: dict[str, str]
) -> dict[str, str | None]:
    """The VLAN GROUP name is a function of the switch names.

    Given the set of all connections to a single baremetal node,

    Assert that data_center is the same for all switches.

    Assert that the switches are spread across no more than two racks.

    Assert that there are exactly two connections to each "network" switch.

    Use the supplied mapping to categorise the connected switches.

    If both switches are in the same rack, the vlan_group name looks like this:

    ["a11-12-1", "a11-12-2"] => "a11-12-network"

    If those switches are spread across a pair of racks, the VLAN name has both
    racks separated by a slash:

    ["a11-12-1", "a11-13-1"] => "a11-12/a11-13-network"
    """
    assert_consistent_data_center(ports)
    assert_single_or_paired_racks(ports)
    assert_switch_names_have_known_suffixes(ports, mapping)

    vlan_groups = group_by_switch_category(ports, mapping)

    assert_redundant_network_connections(vlan_groups)

    vlan_group_names = {}
    for switch_category, ports_in_group in vlan_groups.items():
        rack_names = {p.rack_name for p in ports_in_group}
        vlan_group_name = "/".join(sorted(rack_names)) + "-" + switch_category
        for p in ports_in_group:
            vlan_group_names[p.switch_system_name] = vlan_group_name
    return vlan_group_names


def assert_consistent_data_center(ports: Iterable[InspectedPort]):
    data_centers = {p.data_center_name for p in ports}
    if len(data_centers) > 1:
        raise TopologyError("Connected to switches in multiple data centers: %s", ports)


def assert_single_or_paired_racks(ports: Iterable[InspectedPort]):
    network_rack_names = {p.rack_name for p in ports}
    if len(network_rack_names) > 2:
        raise TopologyError("Connected to switches in more than two racks: %s", ports)


def assert_switch_names_have_known_suffixes(
    ports: Iterable[InspectedPort], mapping: dict
):
    for port in ports:
        if port.switch_suffix not in mapping:
            raise TopologyError(
                f"Switch suffix {port.switch_system_name} is not present "
                f"in the mapping configured in "
                f"ironic_understack.switch_name_vlan_group_mapping. "
                f"Recognised suffixes are: {mapping.keys()}"
            )


def assert_redundant_network_connections(vlan_groups: dict[str, list[InspectedPort]]):
    network_ports = vlan_groups.get("network", [])
    switch_names = {p.switch_system_name for p in network_ports}
    if len(switch_names) != 2:
        raise TopologyError(
            "Expected connections to exactly two network switches, got %s",
            network_ports,
        )


def group_by_switch_category(
    ports: list[InspectedPort], mapping: dict[str, str]
) -> dict[str, list[InspectedPort]]:
    groups = {}

    for port in ports:
        switch_category = mapping[port.switch_suffix]

        if switch_category not in groups:
            groups[switch_category] = []

        groups[switch_category].append(port)

    return groups
