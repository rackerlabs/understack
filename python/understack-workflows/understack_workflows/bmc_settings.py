import logging
import os

from understack_workflows.bmc import Bmc

logger = logging.getLogger(__name__)

REQUIRED_VALUES = {
    "SNMP.1.AgentEnable": "Enabled",
    "SNMP.1.SNMPProtocol": "All",
    "SNMP.1.AgentCommunity": "public",
    "SNMP.1.AlertPort": 161,
    "SwitchConnectionView.1.Enable": "Enabled",
    "NTPConfigGroup.1.NTPEnable": "Enabled",
    "Time.1.Timezone": "UTC",
    "IPv4.1.DNS1": os.getenv("DNS_SERVER_IPV4_ADDR_1"),
    "IPv4.1.DNS2": os.getenv("DNS_SERVER_IPV4_ADDR_2"),
    "NTPConfigGroup.1.NTP1": os.getenv("NTP_SERVER_IPV4_ADDR_1"),
    "NTPConfigGroup.1.NTP2": os.getenv("NTP_SERVER_IPV4_ADDR_2"),
}

# When we GET Enum-type keys we can expect a string like "Enabled".
# To change that key requires us to POST the numeric string like "1".
VALUES_TO_POST = REQUIRED_VALUES | {
    "SNMP.1.AgentEnable": "1",
    "SNMP.1.SNMPProtocol": "0",
}

IDRAC10_ATTRIBUTE_ALIASES = {
    "IPv4.1.DNS1": "IPv4.1.StaticDNS1",
    "IPv4.1.DNS2": "IPv4.1.StaticDNS2",
}


class BiosSettingException(Exception):
    """Exception when a required key are not present."""


def update_dell_drac_settings(bmc: Bmc) -> dict:
    """Check and update DRAC settings to standard as required.

    Returns the changes that were made
    """
    attribute_path = bmc.manager_attributes_path
    current_values = bmc.redfish_request(attribute_path)["Attributes"]

    uses_idrac10_attributes = not attribute_path.rstrip("/").endswith("/Attributes")
    required_changes = {}
    required_display_values = {}
    for configured_key, required_value in REQUIRED_VALUES.items():
        key = (
            IDRAC10_ATTRIBUTE_ALIASES.get(configured_key, configured_key)
            if uses_idrac10_attributes
            else configured_key
        )
        if not required_value:
            logger.warning(
                "We have no required value configured for BMC attribute '%s'", key
            )
        elif key not in current_values:
            logger.warning("%s has no BMC attribute '%s'", bmc, key)
        elif current_values[key] == required_value:
            logger.info("%s: '%s' already set to '%s'", bmc, key, required_value)
        else:
            required_changes[key] = VALUES_TO_POST[configured_key]
            required_display_values[key] = required_value

    if required_changes:
        logger.info("%s Updating DRAC settings:", bmc)
        for k in required_changes:
            logger.info(
                "  %s: %s->%s", k, current_values[k], required_display_values[k]
            )

        payload = {"Attributes": required_changes}
        bmc.redfish_request(attribute_path, payload=payload, method="PATCH")

        logger.info("%s DRAC settings have been updated", bmc)

    if not required_changes:
        logger.info("%s all required DRAC settings present and correct", bmc)

    return required_changes
