from typing import ClassVar

from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.ironic_wrapper import ironic_ports_for_node

LOG = logging.getLogger(__name__)

PXE_BIOS_NAME_PREFIXES = ["NIC.Integrated", "NIC.Slot"]


class PortBiosNameHook(base.InspectionHook):
    """Set bios_name, pxe_enabled, local_link_connection and physical_network.

    Populates extra.bios_name and port name from inspection inventory, then
    determines PXE-enabled ports from node.extra["enrolled_pxe_ports"]
    (populated during enrolment). If that data is unavailable, all
    NIC.Integrated.* and NIC.Slot.* ports are treated as PXE-enabled.

    PXE ports get pxe_enabled=True plus placeholder physical_network and
    local_link_connection values that neutron requires.
    """

    dependencies: ClassVar[list[str]] = ["ports"]

    def __call__(self, task, inventory, plugin_data):
        inspected_interfaces = inventory.get("interfaces")
        if not inspected_interfaces:
            LOG.error("No interfaces in inventory for node %s", task.node.uuid)
            return

        interface_names = {
            i["mac_address"].upper(): i["name"] for i in inspected_interfaces
        }

        pxe_nics = _enrolled_pxe_nics(task)

        for baremetal_port in ironic_ports_for_node(task.context, task.node.id):
            mac = baremetal_port.address.upper()
            bios_name = interface_names.get(mac)

            _set_port_extra(baremetal_port, mac, bios_name)
            _set_port_name(baremetal_port, mac, bios_name, task.node.name)

            is_pxe = bios_name is not None and any(
                pxe_nic.startswith(bios_name) or bios_name.startswith(pxe_nic)
                for pxe_nic in pxe_nics
            )

            if baremetal_port.pxe_enabled != is_pxe:
                LOG.info(
                    "Port %s (%s) pxe_enabled %s -> %s",
                    mac,
                    bios_name,
                    baremetal_port.pxe_enabled,
                    is_pxe,
                )
                baremetal_port.pxe_enabled = is_pxe
                baremetal_port.save()

            if is_pxe:
                _set_port_physical_network(baremetal_port, mac)
                _set_port_local_link_connection(baremetal_port, mac)


def _enrolled_pxe_nics(task) -> list[str]:
    """Read enrolled PXE NIC names from node.extra, or use broad prefixes."""
    enrolled_pxe_nics = task.node.extra.get("enrolled_pxe_ports")
    if enrolled_pxe_nics is None:
        LOG.warning(
            "Node %s extra.enrolled_pxe_ports is missing, "
            "setting pxe flag on all interfaces starting %s.",
            task.node.uuid,
            PXE_BIOS_NAME_PREFIXES,
        )
        return PXE_BIOS_NAME_PREFIXES

    LOG.info(
        "Set node %s pxe flag on interfaces from extra.enrolled_pxe_ports %s",
        task.node.uuid,
        enrolled_pxe_nics,
    )
    return enrolled_pxe_nics


def _set_port_extra(baremetal_port, mac, required_bios_name):
    extra = baremetal_port.extra
    current_bios_name = extra.get("bios_name")
    if current_bios_name != required_bios_name:
        LOG.info(
            "Port %(mac)s updating bios_name from %(old)s to %(new)s",
            {"mac": mac, "old": current_bios_name, "new": required_bios_name},
        )

        if required_bios_name:
            extra["bios_name"] = required_bios_name
        else:
            extra.pop("bios_name", None)

        baremetal_port.extra = extra
        baremetal_port.save()


def _set_port_name(baremetal_port, mac, required_bios_name, node_name):
    if required_bios_name:
        required_port_name = node_name + ":" + required_bios_name
        if baremetal_port.name != required_port_name:
            LOG.info(
                "Port %s changing name from %s to %s",
                mac,
                baremetal_port.name,
                required_port_name,
            )
            baremetal_port.name = required_port_name
            baremetal_port.save()


def _set_port_physical_network(baremetal_port, mac):
    if not baremetal_port.physical_network:
        LOG.info("Port %s changing physical_network from None to 'enrol'", mac)
        baremetal_port.physical_network = "enrol"
        baremetal_port.save()


def _set_port_local_link_connection(baremetal_port, mac):
    if not baremetal_port.local_link_connection:
        baremetal_port.local_link_connection = {
            "port_id": "None",
            "switch_id": "00:00:00:00:00:00",
            "switch_info": "None",
        }
        LOG.info(
            "Port %s changing local_link_connection from None to %s",
            mac,
            baremetal_port.local_link_connection,
        )
        baremetal_port.save()
