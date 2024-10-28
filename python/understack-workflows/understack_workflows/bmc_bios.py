from understack_workflows.bmc import Bmc
from understack_workflows.bmc import RedfishError
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

REDFISH_BIOS_PATH = "/redfish/v1/Systems/System.Embedded.1/Bios"

REQUIRED_BIOS_SETTINGS = {
    "PxeDev1EnDis": "Enabled",
    "PxeDev1Interface": "NIC.Slot.1-1",
    "HttpDev1Interface": "NIC.Slot.1-1",
    "TimeZone": "UTC",
}


def update_dell_bios_settings(bmc: Bmc) -> dict:
    """Check and update BIOS settings to standard as required.

    Any changes take effect on next server reboot.

    Returns the changes that were made
    """
    current_settings = bmc.redfish_request(REDFISH_BIOS_PATH)["Attributes"]

    required_changes = {
        k: v for k, v in REQUIRED_BIOS_SETTINGS.items() if current_settings[k] != v
    }

    if required_changes:
        logger.info(f"{bmc} Updating BIOS settings: {required_changes}")
        patch_bios_settings(bmc, required_changes)
        logger.info(f"{bmc} BIOS settings will be updated on next server boot")
    else:
        logger.info(f"{bmc} all required BIOS settings present and correct")

    return required_changes


def patch_bios_settings(bmc: Bmc, new_settings: dict):
    path = f"{REDFISH_BIOS_PATH}/Settings"
    payload = {
        "@Redfish.SettingsApplyTime": {"ApplyTime": "OnReset"},
        "Attributes": new_settings,
    }
    try:
        bmc.redfish_request(path, payload=payload, method="PATCH")
    except RedfishError as e:
        if "Pending configuration values" in repr(e):
            logger.info(f"{bmc} BIOS settings job already queued, ignoring.")
            return
        else:
            raise (e) from None
