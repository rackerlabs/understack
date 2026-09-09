"""Shared helpers for firewall (netdev appliance) metadata.

Used by enroll-fw: for a new/re-enrollable node the metadata is handed to the
shared netdev engine so it is written inside the enrollment lifecycle; for an
in-service (active) node apply_node_metadata patches it directly, in place.
"""

import logging

from ironicclient.common.utils import args_array_to_patch

logger = logging.getLogger(__name__)


def firewall_metadata(
    *,
    management_ip: str = "",
    management_switch: str = "",
    management_switch_port: str = "",
    mate_serial: str = "",
    serial: str = "",
    vendor: str = "",
    model: str = "",
) -> tuple[dict, dict, dict]:
    """Build (driver_info, extra, properties) from the firewall fields.

    Only non-empty values are included. Management access goes in driver_info
    (mirroring how servers store redfish_address); the device serial and HA mate
    serial go in extra; vendor/model go in properties (which the Nautobot device
    sync reads). external_cmdb_id is not handled here -- the caller decides where
    it goes (the enroll engine folds it into extra; the metadata patch adds it
    explicitly).
    """
    driver_info = {
        key: value
        for key, value in {
            "management_ip": management_ip,
            "management_switch": management_switch,
            "management_switch_port": management_switch_port,
        }.items()
        if value
    }
    extra = {
        key: value
        for key, value in {"serial": serial, "mate_serial": mate_serial}.items()
        if value
    }
    properties = {
        key: value for key, value in {"vendor": vendor, "model": model}.items() if value
    }
    return driver_info, extra, properties


def apply_node_metadata(
    client, node, driver_info: dict, extra: dict, properties: dict | None = None
) -> None:
    """Diff-patch driver_info/extra/properties onto a node (any provision state).

    Only the supplied keys are considered; keys the request does not mention are
    left untouched.
    """
    node_driver_info = getattr(node, "driver_info", None) or {}
    node_extra = getattr(node, "extra", None) or {}
    node_properties = getattr(node, "properties", None) or {}

    updates = []
    for key, value in driver_info.items():
        if node_driver_info.get(key) != value:
            updates.append(f"driver_info/{key}={value}")
    for key, value in extra.items():
        if node_extra.get(key) != value:
            updates.append(f"extra/{key}={value}")
    for key, value in (properties or {}).items():
        if node_properties.get(key) != value:
            updates.append(f"properties/{key}={value}")

    if not updates:
        logger.info("[node:%s] Firewall metadata already up to date", node.uuid)
        return

    logger.info("[node:%s] Updating firewall metadata %s", node.uuid, updates)
    client.update_node(node.uuid, args_array_to_patch("add", updates))
