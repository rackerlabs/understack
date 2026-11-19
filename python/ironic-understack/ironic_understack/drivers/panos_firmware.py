"""Firmware interface for PAN-OS (Palo Alto) appliances."""

import requests
from ironic import objects
from ironic.common import exception
from ironic.drivers import base
from oslo_log import log

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


class PanosFirmware(base.FirmwareInterface):
    """Record the software versions a PAN-OS appliance reports.

    Updating is not implemented; this only populates the node's firmware
    components so the running PAN-OS release and content versions are visible
    through the Ironic API.
    """

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

        settings = _components_from_system_info(system)
        if not settings:
            raise exception.UnsupportedDriverExtension(
                driver=task.node.driver, extension="firmware components"
            )
        _sync(task, settings)


def _components_from_system_info(system: dict[str, str]) -> list[dict]:
    settings = []
    for field, component in COMPONENT_FIELDS:
        version = system.get(field, "")
        if version in NOT_INSTALLED:
            continue
        settings.append(
            {
                "component": component,
                "current_version": version,
                "vendor": None,
                "model": None,
                "serial_number": None,
            }
        )
    for setting in settings:
        # The appliance itself is the one thing here with an identity.
        if setting["component"] == "panos":
            setting.update(
                vendor=VENDOR,
                model=system.get("model") or None,
                serial_number=system.get("serial") or None,
            )
    return settings


def _sync(task, settings: list[dict]) -> None:
    node_id = task.node.id
    create_list, update_list, _ = (
        objects.FirmwareComponentList.sync_firmware_components(
            task.context, node_id, settings
        )
    )
    for new in create_list:
        objects.FirmwareComponent(
            task.context,
            node_id=node_id,
            component=new["component"],
            current_version=new["current_version"],
            vendor=new["vendor"],
            model=new["model"],
            serial_number=new["serial_number"],
        ).create()
    for up in update_list:
        existing = objects.FirmwareComponent.get(
            task.context, node_id=node_id, name=up["component"]
        )
        if existing.current_version != up["current_version"]:
            existing.last_version_flashed = up["current_version"]
            existing.current_version = up["current_version"]
        existing.vendor = up["vendor"]
        existing.model = up["model"]
        existing.serial_number = up["serial_number"]
        existing.save()
