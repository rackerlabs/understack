import re

from ironic import objects
from ironic.common import exception
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

LOG = logging.getLogger(__name__)


class InspectHookChassisModel(base.InspectionHook):
    """Update baremetal node properties with chassis model number from inventory.

    We set both a baremetal node property and a trait.
    """

    def __call__(self, task, inventory, _plugin_data):
        node = task.node
        chassis_model = _extract_chassis_model(node, inventory)
        manufacturer = _extract_manufacturer(node, inventory)
        trait_name = _trait_name(manufacturer, chassis_model)
        _set_node_traits(task, "CUSTOM_CHASSIS_MODEL_", trait_name)


def _set_node_traits(task, prefix: str, required_trait: str):
    """Manage the subset of node traits whose names begin with `prefix`."""
    node = task.node
    existing_traits = node.traits.get_trait_names()

    required_traits = {x for x in existing_traits if not x.startswith(prefix)}
    required_traits.add(required_trait)

    LOG.debug(
        "Checking traits for node %s: existing=%s required=%s",
        node.uuid,
        existing_traits,
        required_trait,
    )
    if existing_traits != required_traits:
        objects.TraitList.create(task.context, task.node.id, required_traits)
        node.save()


def _extract_chassis_model(node, inventory: dict) -> str:
    """Extract up the system_vendor product name.

    Return a cleaned-up string like "POWEREDGE_R7615".
    """
    chassis_model = inventory.get("system_vendor", {}).get("product_name")
    if chassis_model is None:
        raise exception.InvalidNodeInventory(
            node=node.uuid, reason="Missing product_name in inventory data."
        )
    return re.sub(r" \(.*\)", "", str(chassis_model))


def _extract_manufacturer(node, inventory: dict) -> str:
    """Extract up the system ventor manufacturer name.

    Return a cleaned-up string like "Dell" or "HP".
    """
    name = inventory.get("system_vendor", {}).get("manufacturer")
    if name is None:
        raise exception.InvalidNodeInventory(
            node=node.uuid, reason="No manufacturer found in inventory data."
        )

    if "DELL" in name.upper():
        return "Dell"
    elif "HP" in name.upper():
        return "HP"
    else:
        return name.replace(" ", "_")


def _trait_name(manufacturer: str, chassis_model: str) -> str:
    """The node trait that should be present on this node."""
    return f"{manufacturer}_#{chassis_model}".upper().replace(" ", "_")
