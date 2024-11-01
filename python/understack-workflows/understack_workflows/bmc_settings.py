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
}

REDFISH_PATH = "/redfish/v1/Managers/iDRAC.Embedded.1/Attributes"


def update_dell_drac_settings(bmc: Bmc) -> dict:
    """Check and update DRAC settings to standard as required.

    Returns the changes that were made
    """
    current_values = bmc.redfish_request(REDFISH_PATH)["Attributes"]

    for key in STANDARD.keys():
        if key not in current_values:
            raise Exception(f"{bmc} has no BMC attribute {key}")

    required_changes = {
        k: x["new_value"]
        for k, x in STANDARD.items()
        if current_values[k] != x["expect"]
    }

    if required_changes:
        logger.info(f"{bmc} Updating DRAC settings:")
        for k in required_changes.keys():
            logger.info(f"  {k}: {current_values[k]}->{STANDARD[k]['expect']}")

        payload = {"Attributes": required_changes}
        bmc.redfish_request(REDFISH_PATH, payload=payload, method="PATCH")

        logger.info(f"{bmc} DRAC settings have been updated")
    else:
        logger.info(f"{bmc} all required DRAC settings present and correct")

    return required_changes
