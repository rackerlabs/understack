import logging

from understack_workflows.bmc import Bmc
from understack_workflows.bmc import RedfishRequestError

logger = logging.getLogger(__name__)


def required_bios_settings(pxe_interface: str) -> dict:
    """Return adjusted Bios settings map for BMC."""
    return {
        "PxeDev1EnDis": "Disabled",
        "HttpDev1EnDis": "Enabled",
        "HttpDev1Interface": pxe_interface,
        # at this time ironic conductor returns http URLs
        # when its serving data from its own http server
        "HttpDev1TlsMode": "None",
        "TimeZone": "UTC",
        # This disables a virtual USB NIC that was confusing vmware.  This
        # device allows the operating system to talk to the iDRAC.  Disabling it
        # closes down one of the ways that the operating system can make changes
        # to the iDRAC.  We want to retain complete control over the iDRAC
        # because we rely upon it for cleaning, power cycle, and other critical
        # tasks:
        "OS-BMC.1.AdminState": "Disabled",
        # This closes down IPMI, which we don't use anyhow:
        "IPMILan.1.Enable": "Disabled",
    }


def required_change_for_bios_setting(
    key: str,
    required_value: str,
    current_settings: dict,
    pending_settings: dict,
) -> str | None:
    active_value = current_settings.get(key)
    pending_value = pending_settings.get(key)

    if active_value is None:
        logger.debug("X - BIOS has no %s setting", key)
        return None

    if pending_value == required_value:
        logger.debug(
            "[✓] %s currently %r but already pending update to %r",
            key,
            active_value,
            required_value,
        )
        return None

    if pending_value is not None:
        logger.debug(
            "⚠ - %s should be set to %r but with pending update to %r, updating",
            key,
            required_value,
            pending_value,
        )
        return required_value

    if active_value == required_value:
        logger.debug("✓ - %s already set to %r", key, required_value)
        return None

    logger.debug(
        "→ - %s is currently %r, setting to %r",
        key,
        active_value,
        required_value,
    )
    return required_value


def update_dell_bios_settings(bmc: Bmc, pxe_interface: str) -> dict:
    """Check and update BIOS settings to standard as required.

    Any changes take effect on next server reboot.

    Returns the changes that were made
    """
    current_settings = bmc.redfish_request(bmc.system_path + "/Bios")["Attributes"]
    pending_settings = bmc.redfish_request(bmc.system_path + "/Bios/Settings").get(
        "Attributes", {}
    )
    required_settings = required_bios_settings(pxe_interface)

    logger.info("%s Checking BIOS settings", bmc)
    required_changes = {}
    for key, required_value in required_settings.items():
        required_change = required_change_for_bios_setting(
            key,
            required_value,
            current_settings,
            pending_settings,
        )
        if required_change is None:
            continue
        required_changes[key] = required_change

    if required_changes:
        patch_bios_settings(bmc, required_changes)
        logger.info("%s BIOS settings will be updated on next server boot.", bmc)
    else:
        logger.info("%s all required BIOS settings present and correct.", bmc)

    return required_changes


def patch_bios_settings(bmc: Bmc, new_settings: dict):
    """Apply Bios settings to BMC."""
    settings_path = f"{bmc.system_path}/Bios/Settings"
    payload = {
        "@Redfish.SettingsApplyTime": {"ApplyTime": "OnReset"},
        "Attributes": new_settings,
    }
    try:
        bmc.redfish_request(settings_path, payload=payload, method="PATCH")
    except RedfishRequestError as e:
        if "Pending configuration values" in repr(e):
            logger.info("%s BIOS settings job already queued, ignoring.", bmc)
            return
        raise
