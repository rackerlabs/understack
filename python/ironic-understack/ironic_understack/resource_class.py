# from ironic.drivers.modules.inspector.hooks import base
from pathlib import Path

from flavor_matcher.device_type import DeviceType
from flavor_matcher.machine import Machine
from flavor_matcher.matcher import Matcher
from ironic.common import exception
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)

DEVICE_TYPES = DeviceType.from_directory(Path(CONF.ironic_understack.device_types_dir))
LOG.info("Loaded %d device types.", len(DEVICE_TYPES))


class NoMatchError(Exception):
    pass


class ResourceClassHook(base.InspectionHook):
    """Hook to set the node's resource_class based on the inventory."""

    def __call__(self, task, inventory, plugin_data):
        """Update node resource_class with matched resource class."""
        # clear the existing resource_class
        task.node.resource_class = None

        try:
            memory_mb = inventory["memory"]["physical_mb"]
            disk_size_gb = int(int(inventory["disks"][0]["size"]) / 10**9)
            cpu_model_name = inventory["cpu"]["model_name"]

            # Extract additional fields for new Machine API
            cpu_cores = inventory.get("cpu", {}).get("count", 0)
            manufacturer = inventory.get("system_vendor", {}).get("manufacturer", "")
            model_name = inventory.get("system_vendor", {}).get("product_name", "")

            # trim 'Inc.'
            manufacturer = manufacturer.replace("Inc.", "").strip()
            # HP -> HPE
            if manufacturer == "HP":
                manufacturer = "HPE"
            # trim model info of SKUs by taking everything before the (
            model_name = model_name.split("(")[0].strip()

            machine = Machine(
                memory_mb=memory_mb,
                cpu=cpu_model_name,
                cpu_cores=cpu_cores,
                disk_gb=disk_size_gb,
                manufacturer=manufacturer,
                model=model_name,
            )

            resource_class_name = self.classify(machine)

            LOG.info(
                "Discovered resources_class: %s for node %s",
                resource_class_name,
                task.node.uuid,
            )
            task.node.resource_class = resource_class_name
        except (KeyError, ValueError, TypeError):
            msg = (
                f"Inventory has missing hardware information for node {task.node.uuid}."
            )
            LOG.error(msg)
            raise exception.InvalidNodeInventory(
                node=task.node.uuid, reason=msg
            ) from None
        except NoMatchError:
            msg = f"No matching resource class found for {task.node.uuid}"
            LOG.error(msg)

        # always save so that we clear it if we failed to find a match
        task.node.save()

    def classify(self, machine):
        matcher = Matcher(device_types=DEVICE_TYPES)
        match_result = matcher.match(machine)
        if not match_result:
            raise NoMatchError(f"No resource class found for {machine}")
        else:
            device_type, resource_class = match_result
            return resource_class.name
