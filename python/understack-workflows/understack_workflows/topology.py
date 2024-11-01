from understack_workflows.nautobot_device import NautobotDevice


def pxe_interface_name(nautobot_device: NautobotDevice) -> str:
    """Answer the last interface that connects to a -1 switch.

    We choose the last interface sorted alphabetically because we want this to
    favour "NIC.Slot" over "NIC.Integrated", because that follows an arbitrary
    local convention.

    A more correct algorithm would probably be:

    Find the connected switch with a role of "Tenant leaf" that comes first in
    the list of switch names in its vlan_group, sorting alphabetically.

    However the switch roles, etc., don't seem set in stone and so I don't want
    to rely on that data for now.
    """
    switches = switch_connections(nautobot_device)

    for interface_name, switch_name in reversed(switches.items()):
        if switch_name.split(".")[0].endswith("-1"):
            return interface_name

    raise Exception(f"No connection to a -1 switch for PXE, only {switches}")


def switch_connections(nautobot_device: NautobotDevice) -> dict:
    return {
        i.name: i.neighbor_device_name
        for i in nautobot_device.interfaces
        if i.neighbor_device_name
    }
