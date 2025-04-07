# Please keep this in sync with data_center.py in this repo:
VLAN_GROUP_SUFFIXES = {
    "-1": "network",
    "-2": "network",
    "-1f": "storage",
    "-2f": "storage",
    "-3f": "storage-appliance",
    "-4f": "storage-appliance",
    "-1d": "bmc",
}


def for_switch(switch_name: str) -> str:
    switch_name = switch_name.split(".")[0]

    for switch_name_suffix, vlan_group_suffix in VLAN_GROUP_SUFFIXES.items():
        if switch_name.endswith(switch_name_suffix):
            cabinet_name = switch_name.removesuffix(switch_name_suffix)
            return f"{cabinet_name}-{vlan_group_suffix}"

    raise ValueError(
        f"Could not determine the VLAN GROUP name for Switch {switch_name}.  We "
        f"only have a convention to do this for switch names ending "
        f"in one of the suffixes {list(VLAN_GROUP_SUFFIXES.keys())}"
    )
