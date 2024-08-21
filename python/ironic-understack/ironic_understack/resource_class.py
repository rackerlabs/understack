# from ironic.drivers.modules.inspector.hooks import base
from ironic_understack.flavor_spec import FlavorSpec
from ironic.common import exception
from ironic.drivers.modules.inspector.hooks import base
from ironic_understack.machine import Machine
from ironic_understack.matcher import Matcher
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

# temporary until we have a code automatically loading these files
FLAVORS = [
    FlavorSpec(
        name="gp2.tiny",
        memory_gb=32,
        cpu_cores=8,
        cpu_models=["AMD EPYC 9124 16-Core Processor"],
        drives=[200, 200],
        devices=["PowerEdge R7515", "PowerEdge R7615", "PowerEdge R740xd"],
    ),
    FlavorSpec(
        name="gp2.small",
        memory_gb=192,
        cpu_cores=16,
        cpu_models=["AMD EPYC 9124 16-Core Processor"],
        drives=[960, 960],
        devices=["PowerEdge R7515", "PowerEdge R7615", "PowerEdge R740xd"],
    ),
    FlavorSpec(
        name="gp2.medium",
        memory_gb=384,
        cpu_cores=24,
        cpu_models=["AMD EPYC 9254 24-Core Processor"],
        drives=[960, 960],
        devices=["PowerEdge R7515", "PowerEdge R7615"],
    ),
    FlavorSpec(
        name="gp2.large",
        memory_gb=768,
        cpu_cores=48,
        cpu_models=["AMD EPYC 9454 48-Core Processor"],
        drives=[960, 960],
        devices=["PowerEdge R7615"],
    ),
]

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
            msg = (
                f"No matching flavor found for {task.node.uuid}"
            )

    def classify(self, machine):
        # TODO: read the device types repo later
        matcher = Matcher([machine], FLAVORS)
        possible_flavors_for_machine = {
            k: v for (k, v) in matcher.match().items() if len(v) > 0
        }
        try:
            return self._pick_best_flavor(FLAVORS, possible_flavors_for_machine)
        except IndexError as e:
            raise NoMatchError(e)

    def _pick_best_flavor(self, all_flavors, matched_flavors):
        all_specs = {f.name: f for f in all_flavors}

        # For now choose "best" by memory, but this likely needs to be revisisted.
        sorted_flavors = sorted(
            matched_flavors.keys(), key=lambda mf: all_specs[mf].memory_gb, reverse=True
        )
        best_flavor = sorted_flavors[0]
        return best_flavor
