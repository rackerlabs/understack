import logging

from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import InterfaceInfo

logger = logging.getLogger(__name__)

# We try not choose interface whose name contains any of these:
DISQUALIFIED = ["DRAC", "ILO", "NIC.EMBEDDED"]


def guess_pxe_interfaces(
    device_info: ChassisInfo, pxe_switch_macs: set[str] | None = None
) -> list[str]:
    """First 8 interface names, most probable PXE interfaces first."""
    if pxe_switch_macs is None:
        pxe_switch_macs = set()

    candidate_interfaces = {i for i in device_info.interfaces if not disqualified(i)}

    names = [
        i.name
        for i in sorted(
            candidate_interfaces,
            key=lambda i: likelihood(i, pxe_switch_macs),
        )
    ]

    return names[0:7]


def disqualified(interface: InterfaceInfo) -> bool:
    return any(x in interface.name.upper() for x in DISQUALIFIED)


def likelihood(interface: InterfaceInfo, pxe_switch_macs: set[str]) -> list[bool | str]:
    """A value that is sortable.  Lower is better."""
    return [
        # python sort order: false is "better" than true
        not connected_to_known_pxe_switch(interface, pxe_switch_macs),
        not connected_to_any_switch(interface),
        nic_port_number(interface),
        interface.name,  # tiebreaker
    ]


def connected_to_known_pxe_switch(interface: InterfaceInfo, pxe_switch_macs) -> bool:
    return interface.remote_switch_mac_address in pxe_switch_macs


def connected_to_any_switch(interface: InterfaceInfo) -> bool:
    return interface.remote_switch_mac_address is not None


def nic_port_number(interface: InterfaceInfo) -> str:
    """Preference of interface name like NIC.Slot.1-2-1.

    Prefer Lowest partition, then
    prefer Lowest port, then
    prefer Lowest slot number, then
    prefer Integrated over Slot.
    """
    reversed_name = interface.name[::-1]
    return reversed_name
