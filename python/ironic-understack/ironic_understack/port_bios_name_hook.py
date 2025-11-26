from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.ironic_wrapper import ironic_ports_for_node

LOG = logging.getLogger(__name__)


class PortBiosNameHook(base.InspectionHook):
    """Hook to set port.extra.bios_name field from redfish data."""

    # "ports" creates baremetal ports for each physical NIC, be sure to run this
    # first because we will only be updating ports that already exist:
    dependencies = ["ports"]

    def __call__(self, task, inventory, plugin_data):
        """Populate the baremetal_port.extra.bios_name attribute."""
        LOG.debug(f"{__class__} called with {task=!r} {inventory=!r} {plugin_data=!r}")

        inspected_interfaces = inventory.get("interfaces")
        if not inspected_interfaces:
            LOG.error("No interfaces in inventory for node %s", task.node.uuid)
            return

        interface_names = {
            i["mac_address"].upper(): i["name"] for i in inspected_interfaces
        }

        for baremetal_port in ironic_ports_for_node(task.context, task.node.id):
            mac = baremetal_port.address.upper()
            required_bios_name = interface_names.get(mac)
            extra = baremetal_port.extra
            current_bios_name = extra.get("bios_name")

            if current_bios_name != required_bios_name:
                LOG.debug(
                    "Port %(mac)s updating bios_name from %(old)s to %(new)s",
                    {"mac": mac, "old": current_bios_name, "new": required_bios_name}
                )

                if required_bios_name:
                    extra["bios_name"] = required_bios_name
                else:
                    extra.pop("bios_name", None)

                baremetal_port.extra = extra
                baremetal_port.save()
