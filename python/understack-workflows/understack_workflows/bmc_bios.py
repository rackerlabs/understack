from understack_workflows.bmc import Bmc
from understack_workflows.bmc import RedfishError
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

REDFISH_BIOS_PATH = "/redfish/v1/Systems/System.Embedded.1/Bios"


def required_bios_settings(pxe_interface: str) -> dict:
    return {
        "PxeDev1EnDis": "Enabled",
        "PxeDev1Interface": pxe_interface,
        "HttpDev1EnDis": "Enabled",
        "HttpDev1Interface": pxe_interface,
        # at this time ironic conductor returns http URLs
        # when its serving data from its own http server
        "HttpDev1TlsMode": "None",
        "TimeZone": "UTC",
    }


def update_dell_bios_settings(bmc: Bmc, pxe_interface="NIC.Slot.1-1") -> dict:
    """Check and update BIOS settings to standard as required.

    Any changes take effect on next server reboot.

    Returns the changes that were made
    """
    current_settings = bmc.redfish_request(REDFISH_BIOS_PATH)["Attributes"]
    required_settings = required_bios_settings(pxe_interface)

    required_changes = {
        k: v for k, v in required_settings.items() if current_settings[k] != v
    }

    if required_changes:
        logger.info("%s Updating BIOS settings: %s", bmc, required_changes)
        patch_bios_settings(bmc, required_changes)
        logger.info("%s BIOS settings will be updated on next server boot", bmc)
    else:
        logger.info("%s all required BIOS settings present and correct", bmc)

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
            logger.info("%s BIOS settings job already queued, ignoring.", bmc)
            return
        raise
