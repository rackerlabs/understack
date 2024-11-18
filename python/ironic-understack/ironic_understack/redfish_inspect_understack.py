# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
"""
Redfish Inspect Interface modified for Understack
"""

from ironic.drivers.drac import IDRACHardware
from ironic.drivers.modules.drac.inspect import DracRedfishInspect
from ironic.drivers.modules.inspect_utils import get_inspection_data
from ironic.drivers.modules.redfish.inspect import RedfishInspect
from ironic.drivers.redfish import RedfishHardware
from flavor_matcher.flavor_spec import FlavorSpec
from flavor_matcher.machine import Machine
from flavor_matcher.matcher import Matcher
from ironic_understack.conf import CONF
from oslo_log import log
from oslo_utils import units

LOG = log.getLogger(__name__)
FLAVORS = FlavorSpec.from_directory(CONF.ironic_understack.flavors_dir)
LOG.info(f"Loaded {len(FLAVORS)} flavor specifications.")


class FlavorInspectMixin:
    def inspect_hardware(self, task):
        """Inspect hardware to get the hardware properties.

        Inspects hardware to get the essential properties.
        It fails if any of the essential properties
        are not received from the node.

        :param task: a TaskManager instance.
        :raises: HardwareInspectionFailure if essential properties
                 could not be retrieved successfully.
        :returns: The resulting state of inspection.

        """
        upstream_state = super().inspect_hardware(task)  # pyright: ignore reportAttributeAccessIssue

        inspection_data = get_inspection_data(task.node, task.context)

        inventory = inspection_data or {}
        if not inventory:
            LOG.warn(f"No inventory found for node {task.node}")

        inventory = inventory["inventory"]
        LOG.debug(f"Retrieved {inspection_data=}")

        if not (inventory.get("memory") and "physical_mb" in inventory["memory"]):
            LOG.warn("No memory_mb property detected, skipping flavor setting.")
            return upstream_state

        if not (inventory.get("disks") and inventory["disks"][0].get("size")):
            LOG.warn("No disks detected, skipping flavor setting.")
            return upstream_state

        if not (inventory.get("cpu") and inventory["cpu"]["model_name"]):
            LOG.warn("No CPUS detected, skipping flavor setting.")
            return upstream_state

        smallest_disk_gb = min([disk["size"] / units.Gi for disk in inventory["disks"]])
        machine = Machine(
            memory_mb=inventory["memory"]["physical_mb"],
            disk_gb=smallest_disk_gb,
            cpu=inventory["cpu"]["model_name"],
        )

        matcher = Matcher(FLAVORS)
        best_flavor = matcher.pick_best_flavor(machine)
        if not best_flavor:
            LOG.warn(f"No flavor matched for {task.node.uuid}")
            return upstream_state
        LOG.info(f"Matched {task.node.uuid} to flavor {best_flavor}")

        task.node.resource_class = f"baremetal.{best_flavor.name}"
        task.node.save()

        return upstream_state


class UnderstackRedfishInspect(FlavorInspectMixin, RedfishInspect):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        patched_ifaces = RedfishHardware().supported_inspect_interfaces
        patched_ifaces.append(UnderstackDracRedfishInspect)
        setattr(
            RedfishHardware,
            "supported_inspect_interfaces",
            property(lambda _: patched_ifaces),
        )


class UnderstackDracRedfishInspect(FlavorInspectMixin, DracRedfishInspect):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        patched_ifaces = IDRACHardware().supported_inspect_interfaces
        patched_ifaces.append(UnderstackDracRedfishInspect)
        setattr(
            IDRACHardware,
            "supported_inspect_interfaces",
            property(lambda _: patched_ifaces),
        )
