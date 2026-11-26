"""Firmware interface for Cisco NX-OS switches."""

import requests
from ironic.common import exception
from ironic.drivers import base
from oslo_log import log

from ironic_understack.drivers import cisco_nxos_base
from ironic_understack.drivers.cisco_nxos_base import CiscoNxosInterface
from ironic_understack.utils import firmware_components
from ironic_understack.utils import nxos_api

LOG = log.getLogger(__name__)

# ``show version`` fields holding the NX-OS release, newest name first; older
# releases only report the kickstart/system image versions.
NXOS_VERSION_FIELDS = ("nxos_ver_str", "sys_ver_str", "kickstart_ver_str")


class CiscoNxosFirmware(CiscoNxosInterface, base.FirmwareInterface):
    """Record the NX-OS release a switch is running.

    Updating is not implemented; this only populates the node's firmware
    components so the running NX-OS release is visible through the Ironic API.
    """

    def update(self, task, settings):
        raise exception.UnsupportedDriverExtension(
            driver=task.node.driver, extension="firmware update"
        )

    @base.verify_step(priority=5)
    @base.clean_step(priority=0, requires_ramdisk=False)
    @base.service_step(requires_ramdisk=False)
    def cache_firmware_components(self, task):
        """Store or update the switch's NX-OS release on the node."""
        address = task.node.driver_info["nxos_address"]
        try:
            with cisco_nxos_base.client(task.node) as client:
                version = client.show_version()
        except (nxos_api.NxosApiError, requests.RequestException) as e:
            raise exception.IronicException(
                f"Cannot read the firmware version from NX-OS {address}: {e}"
            ) from e
        record_versions(task, version)


def record_versions(task, version: dict) -> None:
    """Store the NX-OS release ``show version`` reported as a firmware component."""
    settings = components_from_show_version(version)
    if not settings:
        raise exception.UnsupportedDriverExtension(
            driver=task.node.driver, extension="firmware components"
        )
    firmware_components.sync(task, settings)


def nxos_version(version: dict) -> str | None:
    """Return the running NX-OS release from ``show version``."""
    return next((v for f in NXOS_VERSION_FIELDS if (v := version.get(f))), None)


def components_from_show_version(version: dict) -> list[dict]:
    """Return the ``nxos`` component, or nothing if no release is reported."""
    release = nxos_version(version)
    if not release:
        return []
    return [
        {
            "component": "nxos",
            "current_version": release,
            # Make, model and serial describe the switch, not its firmware;
            # they are in the inspection data's system_vendor.
            "vendor": None,
            "model": None,
            "serial_number": None,
        }
    ]
