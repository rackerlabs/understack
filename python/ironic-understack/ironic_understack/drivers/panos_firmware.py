"""Firmware interface for PAN-OS (Palo Alto) appliances."""

import requests
from ironic.common import exception
from ironic.drivers import base
from oslo_log import log

from ironic_understack.drivers.panos_base import PanosInterface
from ironic_understack.utils import firmware_components
from ironic_understack.utils import panos_api

LOG = log.getLogger(__name__)

VENDOR = "Palo Alto Networks"

# ``show system info`` field -> Ironic firmware component name. Content
# packages that the appliance has never installed report an empty or "0"
# version and are skipped.
COMPONENT_FIELDS = (
    ("sw-version", "panos"),
    ("app-version", "app-content"),
    ("av-version", "antivirus"),
    ("wildfire-version", "wildfire"),
    ("global-protect-client-package-version", "globalprotect-client"),
    ("device-dictionary-version", "device-dictionary"),
)
NOT_INSTALLED = {"", "0", "unknown", "None"}


class PanosFirmware(PanosInterface, base.FirmwareInterface):
    """Record the software versions a PAN-OS appliance reports.

    Updating is not implemented; this only populates the node's firmware
    components so the running PAN-OS release and content versions are visible
    through the Ironic API.
    """

    def update(self, task, settings):
        raise exception.UnsupportedDriverExtension(
            driver=task.node.driver, extension="firmware update"
        )

    @base.verify_step(priority=5)
    @base.clean_step(priority=0, requires_ramdisk=False)
    @base.service_step(requires_ramdisk=False)
    def cache_firmware_components(self, task):
        """Store or update the appliance's software versions on the node."""
        address = task.node.driver_info["management_ip"]
        client = panos_api.PanosClient(address)
        try:
            client.login()
            system = client.system_info()
        except (panos_api.PanosApiError, requests.RequestException) as e:
            raise exception.IronicException(
                f"Cannot read firmware versions from PAN-OS {address}: {e}"
            ) from e
        record_versions(task, system)


def record_versions(task, system: dict[str, str]) -> None:
    """Store the versions ``show system info`` reported as firmware components."""
    settings = _components_from_system_info(system)
    if not settings:
        raise exception.UnsupportedDriverExtension(
            driver=task.node.driver, extension="firmware components"
        )
    firmware_components.sync(task, settings)


def _components_from_system_info(system: dict[str, str]) -> list[dict]:
    """Return a firmware component for each installed version."""
    # The appliance itself is the one thing here with an identity.
    appliance = {
        "vendor": VENDOR,
        "model": system.get("model") or None,
        "serial_number": system.get("serial") or None,
    }
    return [
        {
            "component": component,
            "current_version": version,
            **(appliance if component == "panos" else dict.fromkeys(appliance)),
        }
        for field, component in COMPONENT_FIELDS
        if (version := system.get(field, "")) not in NOT_INSTALLED
    ]
