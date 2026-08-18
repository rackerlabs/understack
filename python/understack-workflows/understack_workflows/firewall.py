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
) -> tuple[dict, dict]:
    """Build (driver_info, extra) from the firewall fields (non-empty only).

    Management access goes in driver_info (mirroring how servers store
    redfish_address); the HA mate serial goes in extra. external_cmdb_id is not
    handled here -- the caller decides where it goes (the enroll engine folds it
    into extra; the metadata patch adds it explicitly).
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
    extra = {"mate_serial": mate_serial} if mate_serial else {}
    return driver_info, extra


def apply_node_metadata(client, node, driver_info: dict, extra: dict) -> None:
    """Diff-patch driver_info/extra onto an existing node (any provision state).

    Only the supplied keys are considered; keys the request does not mention are
    left untouched.
    """
    node_driver_info = getattr(node, "driver_info", None) or {}
    node_extra = getattr(node, "extra", None) or {}

    updates = []
    for key, value in driver_info.items():
        if node_driver_info.get(key) != value:
            updates.append(f"driver_info/{key}={value}")
    for key, value in extra.items():
        if node_extra.get(key) != value:
            updates.append(f"extra/{key}={value}")

    if not updates:
        logger.info("[node:%s] Firewall metadata already up to date", node.uuid)
        return

    logger.info("[node:%s] Updating firewall metadata %s", node.uuid, updates)
    client.update_node(node.uuid, args_array_to_patch("add", updates))
