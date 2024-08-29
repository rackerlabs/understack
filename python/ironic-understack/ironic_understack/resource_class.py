# from ironic.drivers.modules.inspector.hooks import base
from ironic.common import exception
from ironic.drivers.modules.inspector.hooks import base
from ironic_understack.flavor_spec import FlavorSpec
from ironic_understack.machine import Machine
from ironic_understack.matcher import Matcher
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

FLAVORS = FlavorSpec.from_directory(CONF.ironic_understack.flavors_dir)
LOG.info(f"Loaded {len(FLAVORS)} flavor specifications.")


class NoMatchError(Exception):
    pass


class UndercloudResourceClassHook(base.InspectionHook):
    """Hook to set the node's resource_class based on the inventory."""

    def __call__(self, task, inventory, plugin_data):
        """Update node resource_class with deducted flavor."""

        try:
            memory_mb = inventory["memory"]["physical_mb"]
            disk_size_gb = int(int(inventory["disks"][0]["size"]) / 10**9)
            cpu_model_name = inventory["cpu"]["model_name"]

            machine = Machine(
                memory_mb=memory_mb, cpu=cpu_model_name, disk_gb=disk_size_gb
            )

            resource_class_name = self.classify(machine)

            LOG.info(
                "Discovered resources_class: %s for node %s",
                resource_class_name,
                task.node.uuid,
            )
            task.node.resource_class = resource_class_name
            task.node.save()
        except (KeyError, ValueError, TypeError):
            msg = (
                f"Inventory has missing hardware information for node {task.node.uuid}."
            )
            LOG.error(msg)
            raise exception.InvalidNodeInventory(node=task.node.uuid, reason=msg)
        except NoMatchError:
            msg = f"No matching flavor found for {task.node.uuid}"
            LOG.error(msg)

    def classify(self, machine):
        matcher = Matcher(FLAVORS)
        flavor = matcher.pick_best_flavor(machine)
        if not flavor:
            raise NoMatchError(f"No flavor found for {machine}")
        else:
            return flavor
