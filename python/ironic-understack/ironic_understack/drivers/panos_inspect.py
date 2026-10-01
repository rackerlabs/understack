"""Inspect interface for PAN-OS (Palo Alto) appliances."""

from typing import ClassVar

import requests
from ironic.common import exception
from ironic.common import states
from ironic.drivers import base
from oslo_log import log

from ironic_understack.utils import panos_api

LOG = log.getLogger(__name__)


class PanosInspect(base.InspectInterface):
    """Inspect a PAN-OS appliance over its XML API.

    No ramdisk is involved; everything goes over the management address in
    ``driver_info['management_ip']``, which enroll-fw sets.
    """

    # A firewall has no memory_mb/local_gb/cpu_arch to report.
    ESSENTIAL_PROPERTIES: ClassVar[set] = set()

    def get_properties(self):
        return {
            "management_ip": "Address of the appliance's management interface, "
            "used for the XML API. Required.",
        }

    def validate(self, task):
        if not task.node.driver_info.get("management_ip"):
            raise exception.MissingParameterValue(
                f"Node {task.node.uuid} is missing driver_info management_ip"
            )

    def inspect_hardware(self, task):
        node = task.node
        address = node.driver_info["management_ip"]
        client = panos_api.PanosClient(address)
        try:
            client.login()
            LOG.debug("[node:%s] Logged in to %s", node.uuid, address)
            system = client.system_info()
        except (panos_api.PanosApiError, requests.RequestException) as e:
            raise exception.HardwareInspectionFailure(
                error=f"PAN-OS {address}: {e}"
            ) from e

        _apply_system_info(node, system)

        # TODO: discover data plane connectivity and create ports from it:
        # - show interface all, for the data plane interfaces and their MACs
        # - LLDP neighbors. Interfaces without config don't transmit LLDP, so
        #   this needs to enable LLDP and a transmit-receive profile on them,
        #   commit, wait for neighbors, collect them, then restore the
        #   original config and commit again.
        # - an Ironic port per neighbor named "<node name>:<interface>", with
        #   local_link_connection from the neighbor and the remote interface
        #   as extra["bios_name"]
        # TODO: show high-availability all, recording the HA peer serial in
        # extra["mate_serial"] (which enroll-fw also sets) when HA is enabled.

        node.save()
        return states.MANAGEABLE


def _apply_system_info(node, system: dict[str, str]) -> None:
    """Record what ``show system info`` reported on the node.

    model and serial are also set by enroll-fw from Nautobot, so those are only
    filled in when missing; a disagreement is logged rather than overwritten.
    """
    properties = dict(node.properties)
    extra = dict(node.extra)
    for target, key, field in (
        (properties, "model", "model"),
        (extra, "serial", "serial"),
    ):
        found = system.get(field)
        if not found:
            continue
        if not target.get(key):
            target[key] = found
        elif target[key] != found:
            LOG.warning(
                "[node:%s] Appliance reports %s %r but the node has %r",
                node.uuid,
                key,
                found,
                target[key],
            )
    if system.get("sw-version"):
        properties["firmware_version"] = system["sw-version"]
    node.properties = properties
    node.extra = extra
