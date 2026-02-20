import logging

from understack_workflows.bmc import Bmc
from understack_workflows.bmc import RedfishRequestError

logger = logging.getLogger(__name__)


def required_bios_settings(pxe_interface: str) -> dict:
    """Return adjusted Bios settings map for BMC."""
    return {
        "PxeDev1EnDis": "Enabled",
        "PxeDev1Interface": pxe_interface,
        "HttpDev1EnDis": "Enabled",
        "HttpDev1Interface": pxe_interface,
        # at this time ironic conductor returns http URLs
        # when its serving data from its own http server
        "HttpDev1TlsMode": "None",
        "TimeZone": "UTC",
        # This option is available on newer R7615 and it
        # defaults to Enabled which casues it not to boot:
        "InteractiveMode": "Disabled",
    }


def update_dell_bios_settings(bmc: Bmc, pxe_interface: str) -> dict:
    """Check and update BIOS settings to standard as required.

    Any changes take effect on next server reboot.

    Returns the changes that were made
    """
    current_settings = bmc.redfish_request(bmc.system_path + "/Bios")["Attributes"]
    required_settings = required_bios_settings(pxe_interface)

    required_changes = {
        k: v
        for k, v in required_settings.items()
        if (k in current_settings and current_settings[k] != v)
    }

    missing_keys = {k for k in required_settings.keys() if k not in current_settings}
    if missing_keys:
        logger.info("%s Has no BIOS setting for %s, ignoring.", bmc, missing_keys)

    if required_changes:
        logger.info("%s Updating BIOS settings: %s", bmc, required_changes)
        patch_bios_settings(bmc, required_changes)
        logger.info("%s BIOS settings will be updated on next server boot.", bmc)
    else:
        logger.info("%s No BIOS settings need to be changed.", bmc)

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
