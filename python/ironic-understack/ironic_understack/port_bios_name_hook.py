from typing import ClassVar

from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.ironic_wrapper import ironic_ports_for_node

LOG = logging.getLogger(__name__)

PXE_BIOS_NAME_PREFIXES = ["NIC.Integrated", "NIC.Slot"]


class PortBiosNameHook(base.InspectionHook):
    """Set bios_name, pxe_enabled, local_link_connection and physical_network.

    Runs after the "ports" hook has created a baremetal port for each NIC in the
    box.

    We set the `name` and `extra.bios_name` for each port using the BIOS names
    in the inventory data that was collected by redfish inspection.

    When the native Ironic "ports" hook runs, it creates any missing ports but
    lamentably it sets the "pxe" flag on every port it creates.

    We clear that flag, because it causes neutron to do extra work and assign
    extra IP addresses.  We know that it is a newly-created port and not one
    that we specifically set to PXE, because newly created ports don't have a
    physical_network, whereas we always set that property at the same time we
    set the PXE flag.

    If this node has no PXE ports at all, then we assume that this box has just
    been enrolled and has not yet undergone a successful agent inspection.
    Agent inspection will be the next step, and therefore we need to set up the
    bare minimum that is required by Ironic/Neutron to prepare to boot the IPA
    image.

    Even though PXE is not in use, the provisioning network is still required,
    because that is how the agent communicates with Ironic.  Neutron wants to
    make a port in the provisioning network, and it will error out unless it can
    find a suitable baremetal port.

    We choose one arbitrary baremetal port and we populate its attributes with
    dummy data to enable Ironic/Neutron to do an IPA boot:

      - pxe_enabled=True
      - physical_network="enrol" (placeholder value understood by undersync)
      - local_link_connection set to dummy data as placeholder

    Note that this only works because neutron is not completely controlling the
    DHCP server, so it doesn't matter if we choose the wrong port.  If this
    situation changes then we would need to configure all possible NICs with
    placeholder data, which would result in a configuration for every single
    NIC.
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

        ports = list(ironic_ports_for_node(task.context, task.node.id))
        if not ports:
            LOG.error("No baremetal ports in Ironic for node %s", task.node.uuid)
            return

        for baremetal_port in ports:
            mac = baremetal_port.address.upper()
            bios_name = interface_names.get(mac)

            _set_port_extra(baremetal_port, mac, bios_name)
            _set_port_name(baremetal_port, mac, bios_name, task.node.name)
            _clear_unwanted_pxe(baremetal_port)

        if not any(port.pxe_enabled for port in ports):
            _set_port_pxe_placeholder(ports[0])


def _set_port_pxe_placeholder(baremetal_port):
    LOG.info(
        "Populating port %s with placeholder PXE data to support enroll.",
        baremetal_port.address,
    )
    baremetal_port.pxe_enabled = True
    # Note spelling of "enrol" as required by undersync API:
    baremetal_port.physical_network = "enrol"
    baremetal_port.local_link_connection = {
        "port_id": "None",
        "switch_id": "00:00:00:00:00:00",
        "switch_info": "None",
    }
    baremetal_port.save()


def _clear_unwanted_pxe(baremetal_port):
    if baremetal_port.physical_network:
        return

    if not baremetal_port.pxe_enabled:
        return

    LOG.info("Clearing port %s PXE flag.", baremetal_port.address)
    baremetal_port.pxe_enabled = False
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
