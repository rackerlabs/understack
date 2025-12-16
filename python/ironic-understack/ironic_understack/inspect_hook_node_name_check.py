from ironic.common import exception
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class InspectHookNodeNameCheck(base.InspectionHook):
    """Check baremetal node name against system identity from inventory data.

    Expect the node name to be a string like "Dell_AN3Z23A" consistent with the
    manufacturer and serial number in the inventory data.

    If the node name does not match, abort the inspection process to force
    operator intervention.
    """

    def __call__(self, task, inventory, _plugin_data):
        node = task.node
        sys_data = inventory.get("system_vendor", {})

        serial_number = sys_data.get("sku", sys_data.get("serial_number"))
        if serial_number is None:
            raise exception.InvalidNodeInventory(
                node=node.uuid, reason="No serial number found in inventory data."
            )

        manufacturer = sys_data.get("manufacturer")
        if manufacturer is None:
            raise exception.InvalidNodeInventory(
                node=node.uuid, reason="No manufacturer found in inventory data."
            )

        manufacturer_slug = _manufacturer_slug(manufacturer)

        if node.name == f"{manufacturer}_{serial_number}":
            LOG.debug("Node Name Check passed for node %s", node.uuid)
        else:
            raise RuntimeError(
                "Hardware Identity Crisis with baremetal node %s!  The current "
                "node name %s is inconsistent with its hardware manufacturer "
                "%s and serial number/service tag %s.  If this is a "
                "replacement hardware, the baremetal node should be deleted "
                "and re-enrolled.",
                node.uuid,
                node.name,
                manufacturer_slug,
                serial_number,
            )


def _manufacturer_slug(manufacturer_name: str) -> str:
    name = str(manufacturer_name).upper()
    if "DELL" in name:
        return "Dell"
    elif "HP" in name:
        return "HP"
    else:
        return manufacturer_name.replace(" ", "_")
