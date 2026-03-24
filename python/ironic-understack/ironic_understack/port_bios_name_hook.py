from typing import ClassVar

from ironic.common import exception
from ironic.drivers.modules.inspector.hooks import base
from ironic.objects.bios import BIOSSetting
from oslo_log import log as logging

from ironic_understack.ironic_wrapper import ironic_ports_for_node

LOG = logging.getLogger(__name__)

PXE_BIOS_NAME_PREFIXES = ["NIC.Integrated", "NIC.Slot"]
BIOS_SETTING_NAME = "HttpDev1Interface"


class PortBiosNameHook(base.InspectionHook):
    """Set bios_name, pxe_enabled, local_link_connection and physical_network.

    Populates extra.bios_name and port name from inspection inventory, then
    determines the PXE port from the BIOS HttpDev1Interface setting (populated
    during enrolment).  Falls back to a naming-convention heuristic if the
    BIOS setting is unavailable.

    The PXE port gets pxe_enabled=True plus placeholder physical_network and
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

        pxe_nic = _bios_pxe_nic(task)

        for baremetal_port in ironic_ports_for_node(task.context, task.node.id):
            mac = baremetal_port.address.upper()
            bios_name = interface_names.get(mac)

            _set_port_extra(baremetal_port, mac, bios_name)
            _set_port_name(baremetal_port, mac, bios_name, task.node.name)

            if pxe_nic:
                is_pxe = bios_name is not None and (
                    pxe_nic.startswith(bios_name) or bios_name.startswith(pxe_nic)
                )
            else:
                # Fallback: heuristic based on naming convention
                is_pxe = bios_name == _pxe_interface_name(
                    inspected_interfaces, task.node.uuid
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


def _bios_pxe_nic(task):
    """Read the BIOS PXE NIC FQDD, or return None if unavailable."""
    try:
        task.driver.bios.cache_bios_settings(task)
    except Exception:
        LOG.warning(
            "Cannot cache BIOS settings for node %s, "
            "falling back to naming heuristic for PXE port.",
            task.node.uuid,
        )
        return None

    try:
        setting = BIOSSetting.get(task.context, task.node.id, BIOS_SETTING_NAME)
    except exception.BIOSSettingNotFound:
        LOG.warning(
            "BIOS setting %s not found for node %s, "
            "falling back to naming heuristic for PXE port.",
            BIOS_SETTING_NAME,
            task.node.uuid,
        )
        return None

    if not setting.value:
        LOG.warning(
            "BIOS setting %s is empty for node %s, "
            "falling back to naming heuristic for PXE port.",
            BIOS_SETTING_NAME,
            task.node.uuid,
        )
        return None

    LOG.info(
        "Node %s BIOS %s = %s",
        task.node.uuid,
        BIOS_SETTING_NAME,
        setting.value,
    )
    return setting.value


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
