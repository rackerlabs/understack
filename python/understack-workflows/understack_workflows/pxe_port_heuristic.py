import logging

from understack_workflows.bmc_chassis_info import ChassisInfo

logger = logging.getLogger(__name__)

# We try not choose interface whose name contains any of these:
DISQUALIFIED = ["DRAC", "ILO", "NIC.EMBEDDED"]

# Preferred interfaces, most likely first
NIC_PREFERENCE = [
    "NIC.Integrated.1-1-1",
    "NIC.Integrated.1-1",
    "NIC.Slot.1-1-1",
    "NIC.Slot.1-1",
    "NIC.Integrated.1-2-1",
    "NIC.Integrated.1-2",
    "NIC.Slot.1-2-1",
    "NIC.Slot.1-2",
    "NIC.Slot.1-3-1",
    "NIC.Slot.1-3",
    "NIC.Slot.2-1-1",
    "NIC.Slot.2-1",
    "NIC.Integrated.2-1-1",
    "NIC.Integrated.2-1",
    "NIC.Slot.2-2-1",
    "NIC.Slot.2-2",
    "NIC.Integrated.2-2-1",
    "NIC.Integrated.2-2",
    "NIC.Slot.3-1-1",
    "NIC.Slot.3-1",
    "NIC.Slot.3-2-1",
    "NIC.Slot.3-2",
]


def guess_pxe_interface(
    device_info: ChassisInfo, pxe_switch_macs: set[str] | None = None
) -> str:
    """Determine most probable PXE interface for BMC."""
    if pxe_switch_macs is None:
        pxe_switch_macs = set()

    candidate_interfaces = {
        i
        for i in device_info.interfaces
        if not any(q in i.name.upper() for q in DISQUALIFIED)
    }
    candidate_interface_names = {i.name for i in candidate_interfaces}
    connected_interface_names = {
        i.name for i in candidate_interfaces if i.remote_switch_mac_address
    }
    pxe_connected_interface_names = {
        i.name
        for i in candidate_interfaces
        if i.remote_switch_mac_address in pxe_switch_macs
    }

    for name in NIC_PREFERENCE:
        if name in pxe_connected_interface_names:
            logger.info("PXE port is %s, connected to known pxe switch", name)
            return name

    for name in NIC_PREFERENCE:
        if name in connected_interface_names:
            logger.info("PXE port is %s, the first connected interface", name)
            return name

    for name in NIC_PREFERENCE:
        if name in candidate_interface_names:
            logger.info("PXE port is %s, preferred eligible interface", name)
            return name

    if candidate_interface_names:
        name = min(candidate_interface_names)
        logger.info("PXE port is %s, first eligible interface", name)
        return name

    name = device_info.interfaces[0].name
    logger.info("PXE port is %s, chosen as last resort", name)
    return name
