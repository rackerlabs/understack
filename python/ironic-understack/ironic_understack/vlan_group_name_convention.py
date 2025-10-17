def vlan_group_name(switch_name: str) -> str:
    """The VLAN GROUP name is a function of the switch name.

    Switch hostname convention is site-dependent, but in Rackspace all
    top-of-rack switch names follow the convention: <cabinet-name>-<suffix>
    Example switch names include a2-12-1f and a2-12-1.  (These are normally
    qualified with a site-specific domain name like a2-12-1.iad3.rackspace.net,
    but we are only considering the unqualified name, ignoring everything after
    the first dot).

    It easy to parse the switch name into cabinet and suffix.  Convert the
    switch-name-suffix to vlan-group-suffix using the following mapping:

        1 → network
        2 → network
        1f → storage
        2f → storage
        3f → storage-appliance
        4f → storage-appliance
        1d → bmc

    The VLAN GROUP name results from joining the cabinet name to the new suffix
    with a hyphen. The result is in lower case: <cabinet-name>-<vlan-group-suffix>

    So for example, switch a2-12-1 is in VLAN GROUP a2-12-network.
    """
    # Remove domain suffix if present (everything after first dot)
    switch_name = switch_name.split(".")[0].lower()

    # Split into cabinet and suffix (last component after last hyphen)
    parts = switch_name.rsplit("-", 1)
    if len(parts) != 2:
        raise ValueError(f"Unknown switch name format: {switch_name}")

    cabinet_name, suffix = parts

    # Map suffix to VLAN group suffix
    suffix_mapping = {
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

    vlan_suffix = suffix_mapping.get(suffix)
    if vlan_suffix is None:
        raise ValueError(f"Unknown switch suffix: {suffix}")

    return f"{cabinet_name}-{vlan_suffix}"
