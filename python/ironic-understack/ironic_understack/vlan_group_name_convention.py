from typing import Any, Callable, Iterable
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

    If both switches are in the same rack, the vlan_group name looks like this:

    ["a11-12-1", "a11-12-2"] => "a11-12-network"

    If those switches are spread across a pair of racks, the VLAN name has both
    racks separated by a slash:

    ["a11-12-1", "a11-13-1"] => "a11-12/a11-13-network"

    Non-network switches have a VLAN Group name of None.
    """
    data_centers = {p.data_center_name for p in ports}
    if len(data_centers) > 1:
        raise TopologyError("Connected to switches in multiple data centers: %s", ports)

    network_rack_names = {p.rack_name for p in ports}
    if len(network_rack_names) > 2:
        raise TopologyError("Connected to switches in more than two racks: %s", ports)

    for port in ports:
        if port.switch_suffix not in mapping:
            raise TopologyError(
                f"Switch suffix {port.switch_system_name} is not present "
                f"in the mapping configured in "
                f"ironic_understack.switch_name_vlan_group_mapping. "
                f"Recognised suffixes are: {mapping.keys()}"
            )

    vlan_groups = group_by(ports, lambda port: mapping[port.switch_suffix])

    vlan_group_names = {}
    for switch_category, ports_in_group in vlan_groups.items():
        switch_names = {p.switch_system_name for p in ports_in_group}
        if switch_category == "network" and len(switch_names) != 2:
            raise TopologyError(
                "Expected connections to exactly two network switches, got %s",
                ports_in_group,
            )

        rack_names = {p.rack_name for p in ports_in_group}
        vlan_group_name = "/".join(sorted(rack_names)) + "-" + switch_category

        for p in ports_in_group:
            vlan_group_names[p.switch_system_name] = vlan_group_name
    return vlan_group_names


def group_by(items: Iterable, f: Callable) -> dict[Any, list]:
    groups = {}
    for item in items:
        key = f(item)
        if key not in groups:
            groups[key] = []
        groups[key].append(item)
    return groups
