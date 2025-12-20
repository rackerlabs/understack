from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.ironic_wrapper import ironic_ports_for_node

LOG = logging.getLogger(__name__)

PXE_BIOS_NAME_PREFIXES = ["NIC.Integrated", "NIC.Slot"]


class PortBiosNameHook(base.InspectionHook):
    """Set name, extra.bios_name and pxe_enabled fields from redfish data.

    In addition, this hook ensures that the PXE port has sufficient data to
    allow neutron to boot a new node for inspection.  If the physical_network
    and local_link_connections are not populated, we fill them with placeholder
    data.

    This is necessary because neutron throws errors if the port doesn't have
    those fields filled in.
    """

    # "ports" hook creates baremetal ports for each physical NIC, be sure to run
    # this first because we will only be updating ports that already exist:
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

        pxe_interface = _pxe_interface_name(inspected_interfaces, task.node.uuid)

        for baremetal_port in ironic_ports_for_node(task.context, task.node.id):
            mac = baremetal_port.address.upper()
            required_bios_name = interface_names.get(mac)
            required_pxe = required_bios_name == pxe_interface

            _set_port_extra(baremetal_port, mac, required_bios_name)
            _set_port_pxe_enabled(baremetal_port, mac, required_pxe)
            _set_port_name(baremetal_port, mac, required_bios_name, task.node.name)
            _set_port_physical_network(baremetal_port, mac, required_pxe)
            _set_port_local_link_connection(baremetal_port, mac, required_pxe)


def _set_port_pxe_enabled(baremetal_port, mac, required_pxe):
    if baremetal_port.pxe_enabled != required_pxe:
        LOG.info("Port %s changed pxe_enabled to %s", mac, required_pxe)
        baremetal_port.pxe_enabled = required_pxe
        baremetal_port.save()


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


def _set_port_physical_network(baremetal_port, mac, required_pxe):
    if required_pxe and not baremetal_port.physical_network:
        LOG.info("Port %s changing physical_network from None to 'enrol'", mac)
        baremetal_port.physical_network = "enrol"
        baremetal_port.save()


def _set_port_local_link_connection(baremetal_port, mac, required_pxe):
    if required_pxe and not baremetal_port.local_link_connection:
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


def _pxe_interface_name(inspected_interfaces: list[dict], node_uuid) -> str | None:
    """Use a heuristic to determine our default interface for PXE."""
    names = sorted(i["name"] for i in inspected_interfaces)
    for prefix in PXE_BIOS_NAME_PREFIXES:
        for name in names:
            if name.startswith(prefix):
                return name
    LOG.error(
        "No PXE interface found for node %s.  Expected to find an "
        "interface whose bios_name starts with one of %s",
        node_uuid,
        PXE_BIOS_NAME_PREFIXES,
    )
