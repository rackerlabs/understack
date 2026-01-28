from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo

# We try not choose interface whose name contains any of these:
DISQUALIFIED = ["DRAC", "ILO", "NIC.EMBEDDED"]

# A higher number is more likely to be PXE interface:
NIC_PREFERENCE = {
    "NIC.Integrated.1-1-1": 100,
    "NIC.Integrated.1-1": 99,
    "NIC.Slot.1-1-1": 98,
    "NIC.Slot.1-1": 97,
    "NIC.Integrated.1-2-1": 96,
    "NIC.Integrated.1-2": 95,
    "NIC.Slot.1-2-1": 94,
    "NIC.Slot.1-2": 93,
    "NIC.Slot.1-3-1": 92,
    "NIC.Slot.1-3": 91,
    "NIC.Slot.2-1-1": 90,
    "NIC.Slot.2-1": 89,
    "NIC.Integrated.2-1-1": 88,
    "NIC.Integrated.2-1": 87,
    "NIC.Slot.2-2-1": 86,
    "NIC.Slot.2-2": 85,
    "NIC.Integrated.2-2-1": 84,
    "NIC.Integrated.2-2": 83,
    "NIC.Slot.3-1-1": 82,
    "NIC.Slot.3-1": 81,
    "NIC.Slot.3-2-1": 80,
    "NIC.Slot.3-2": 79,
}


def guess_pxe_interface(device_info: ChassisInfo) -> str:
    """Determine most probable PXE interface for BMC."""
    interface = max(device_info.interfaces, key=_pxe_preference)
    return interface.name


def _pxe_preference(interface: InterfaceInfo) -> list:
    """Relative likelihood that interface is used for PXE.

    Prefer names that are not disqualified.

    After that, prefer interfaces that have an LLDP neighbor.

    Finally, score the interface name according to the list above.
    """
    is_eligible = not any(x in interface.name.upper() for x in DISQUALIFIED)

    link_detected = interface.remote_switch_port_name is not None

    name_preference = NIC_PREFERENCE.get(interface.name, 0)

    return [is_eligible, link_detected, name_preference]
