from understack_workflows.bmc import Bmc
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

# When we read Enum-type keys we can expect a string like "Enabled".
#
# To change that key requires the numeric new_value string like "1".
STANDARD = {
    "SNMP.1.AgentEnable": {"expect": "Enabled", "new_value": "1"},
    "SNMP.1.SNMPProtocol": {"expect": "All", "new_value": "0"},
    "SNMP.1.AgentCommunity": {"expect": "public", "new_value": "public"},
    "SNMP.1.AlertPort": {"expect": 161, "new_value": 161},
    "SwitchConnectionView.1.Enable": {"expect": "Enabled", "new_value": "Enabled"},
}


class BiosSettingException(Exception):
    """Exception when a required key are not present."""


def update_dell_drac_settings(bmc: Bmc) -> dict:
    """Check and update DRAC settings to standard as required.

    Returns the changes that were made
    """
    attribute_path = bmc.manager_path + "/Attributes"
    current_values = bmc.redfish_request(attribute_path)["Attributes"]

    for key, _value in STANDARD.items():
        if key not in current_values:
            raise BiosSettingException(f"{bmc} has no BMC attribute {key}")

    required_changes = {
        k: x["new_value"]
        for k, x in STANDARD.items()
        if current_values[k] != x["expect"]
    }

    if required_changes:
        logger.info("%s Updating DRAC settings:", bmc)
        for k in required_changes.keys():
            logger.info("  %s: %s->%s", k, current_values[k], STANDARD[k]["expect"])

        payload = {"Attributes": required_changes}
        bmc.redfish_request(attribute_path, payload=payload, method="PATCH")

        logger.info("%s DRAC settings have been updated", bmc)
    else:
        logger.info("%s all required DRAC settings present and correct", bmc)

    return required_changes
