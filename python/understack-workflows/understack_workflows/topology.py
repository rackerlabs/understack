from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows.data_center import switch_for_mac


def pxe_interface_name(interfaces: list[InterfaceInfo]) -> str:
    """Answer the interface that connects to a -1 switch with following rules.

    Of the interfaces connected to the "-1" switch,
    select the interface with "Integrated" in the name.
    If non such exists, select the interface with "Slot" in the name.
    If neither exist then cause an error.

    A more correct algorithm would probably be:

    Find the connected switch with a role of "Tenant leaf" that comes first in
    the list of switch names in its vlan_group, sorting alphabetically.

    However the switch roles, etc., don't seem set in stone and so I don't want
    to rely on that data for now.
    """
    switches = switch_connections(interfaces)

    for interface_name, switch_name in switches.items():
        if get_preferred_interface(interface_name, switch_name, "Integrated"):
            return interface_name

    for interface_name, switch_name in switches.items():
        if get_preferred_interface(interface_name, switch_name, "Slot"):
            return interface_name

    raise Exception(f"No connection to a -1 switch for PXE, only {switches}")


def get_preferred_interface(interface_name, switch_name, keyword):
    """Check if the interface matches the given keyword and hostname ends with '-1'.

    more on this related to convention.
    https://docs.undercloud.rackspace.net/architecture-decisions/adr014-vlan-group-names/#decision.
    """
    return keyword in interface_name and switch_name.split(".")[0].endswith("-1")


def switch_connections(interfaces: list[InterfaceInfo]) -> dict[str, str]:
    return {
        i.name: switch_for_mac(
            i.remote_switch_mac_address, i.remote_switch_port_name
        ).name
        for i in interfaces
        if i.remote_switch_mac_address and i.remote_switch_port_name
    }
