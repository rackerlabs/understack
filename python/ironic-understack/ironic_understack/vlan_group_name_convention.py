def vlan_group_name(switch_name: str, mapping: dict[str, str]) -> str:
    """The VLAN GROUP name is a function of the switch name.

    Top-of-rack switch hostname is required to follow the convention:

      <cabinet-name>-<suffix>

    We only consider the unqualified name, ignoring everything after the first
    dot.

    The switch name suffix must be one of the keys in the supplied mapping.  The
    corresponding value is used to name the VLAN Group (aka physical network).

    The VLAN GROUP name results from joining the cabinet name to the new suffix
    with a hyphen.

    >>> vlan_group_name("a123-20-1", {"1": "network"})
    >>> "a123-20-network"
    """
    switch_name = switch_name.split(".")[0].lower()

    parts = switch_name.rsplit("-", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Unknown switch name format: {switch_name} - this hook requires "
            f"that switch names follow the convention <cabinet-name>-<suffix>"
        )

    cabinet_name, suffix = parts

    vlan_suffix = mapping.get(suffix)
    if vlan_suffix is None:
        raise ValueError(
            f"Switch suffix {suffix} is not present in the mapping configured "
            f"in ironic_understack.switch_name_vlan_group_mapping.  Recognised "
            f"suffixes are: {mapping.keys()}"
        )

    return f"{cabinet_name}-{vlan_suffix}"
