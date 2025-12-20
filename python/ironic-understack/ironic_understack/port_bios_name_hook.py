from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.ironic_wrapper import ironic_ports_for_node

LOG = logging.getLogger(__name__)


class PortBiosNameHook(base.InspectionHook):
    """Set port.extra.bios_name and pxe_enabled fields from redfish data."""

    # "ports" creates baremetal ports for each physical NIC, be sure to run this
    # first because we will only be updating ports that already exist:
    dependencies = ["ports"]

    def __call__(self, task, inventory, plugin_data):
        """Populate the baremetal_port.extra.bios_name attribute."""
        inspected_interfaces = inventory.get("interfaces")
        if not inspected_interfaces:
            LOG.error("No interfaces in inventory for node %s", task.node.uuid)
            return

        interface_names = {
            i["mac_address"].upper(): i["name"] for i in inspected_interfaces
        }

        pxe_interface = _pxe_interface_name(inspected_interfaces)

        for baremetal_port in ironic_ports_for_node(task.context, task.node.id):
            mac = baremetal_port.address.upper()
            required_bios_name = interface_names.get(mac)
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

            required_pxe = required_bios_name == pxe_interface
            if baremetal_port.pxe_enabled != required_pxe:
                LOG.info("Port %s changed pxe_enabled to %s", mac, required_pxe)
                baremetal_port.pxe_enabled = required_pxe
                baremetal_port.save()

            if required_bios_name:
                required_port_name = task.node.name + ":" + required_bios_name
                if baremetal_port.name != required_port_name:
                    LOG.info(
                        "Port %s changing name from %s to %s",
                        mac,
                        baremetal_port.name,
                        required_port_name,
                    )
                    baremetal_port.name = required_port_name


def _pxe_interface_name(inspected_interfaces: list[dict]) -> str:
    """Use a heuristic to determine our default interface for PXE."""
    names = sorted(i["name"] for i in inspected_interfaces)
    for prefix in ["NIC.Integrated", "NIC.Slot"]:
        for name in names:
            if name.startswith(prefix):
                return name
