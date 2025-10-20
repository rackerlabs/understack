import binascii
from typing import Any

import netaddr
import openstack
from construct import core
from ironic import objects
from ironic.common import exception
from ironic.drivers.modules.inspector import lldp_tlvs
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

import ironic_understack.vlan_group_name_convention

LOG = logging.getLogger(__name__)

LldpData = list[tuple[int, str]]

class UpdateBaremetalPortsHook(base.InspectionHook):
    """Hook to update ports according to LLDP data."""

    dependencies = ["validate-interfaces"]

    def __call__(self, task, inventory, plugin_data):
        """Update Ports' local_link_info and physnet based on LLDP data.

        Process the LLDP packet fields for each NIC in the inventory.

        Updates attributes of the baremetal port:

        - local_link_info.port_id (e.g. "Ethernet1/1")
        - local_link_info.switch_id (e.g. "aa:bb:cc:dd:ee:ff")
        - local_link_info.switch_info (e.g. "a1-1-1.ord1")
        - physical_network (e.g. "a1-1-network")

        Also adds or removes node "traits" based on the inventory data.  We
        control the trait "CUSTOM_STORAGE_SWITCH".
        """
        LOG.debug(f"{__class__} called with {task=!r} {inventory=!r} {plugin_data=!r}")

        lldp_raw: dict[str, LldpData] = plugin_data.get("lldp_raw") or {}
        node_uuid: str = task.node.id
        interfaces: list[dict] = inventory["interfaces"]
        # The all_interfaces field in plugin_data is provided by the
        # validate-interfaces hook, so it is a dependency for this hook
        all_interfaces: dict[str, dict] = plugin_data["all_interfaces"]
        context = task.context
        vlan_groups: set[str] = set()

        for iface in interfaces:
            if iface["name"] not in all_interfaces:
                # This interface was not "validated" so don't bother with it
                continue

            mac_address = iface["mac_address"]
            port = objects.port.Port.get_by_address(context, mac_address)
            if not port:
                LOG.debug(
                    "Skipping LLDP processing for interface %s of node "
                    "%s: matching port not found in Ironic.",
                    mac_address,
                    node_uuid,
                )
                continue

            lldp_data = lldp_raw.get(iface["name"]) or iface.get("lldp")
            if lldp_data is None:
                LOG.warning(
                    "No LLDP data found for interface %s of node %s",
                    mac_address,
                    node_uuid,
                )
                continue

            local_link_connection = _parse_lldp(lldp_data, node_uuid)
            vlan_group = vlan_group_name(local_link_connection)

            _set_local_link_connection(port, node_uuid, local_link_connection)
            _update_port_physical_network(port, vlan_group)
            if vlan_group:
                vlan_groups.add(vlan_group)
        _update_node_traits(task, vlan_groups)


def _set_local_link_connection(port: Any, node_uuid: str, local_link_connection: dict):
    try:
        LOG.debug("Updating port %s for node %s local_link_connection %s",
                  port.id, node_uuid, local_link_connection)
        port.local_link_connection = local_link_connection
        port.save()
    except exception.IronicException as e:
        LOG.warning(
            "Failed to update port %(uuid)s for node %(node)s. Error: %(error)s",
            {"uuid": port.id, "node": node_uuid, "error": e},
        )


def _parse_lldp(lldp_data: LldpData, node_id: str) -> dict[str, str]:
    """Convert Ironic's "lldp_raw" format to local_link dict."""
    try:
        decoded = {}
        for tlv_type, tlv_value in lldp_data:
            if tlv_type not in decoded:
                decoded[tlv_type] = []
            decoded[tlv_type].append(bytearray(binascii.unhexlify(tlv_value)))

        port_id = _extract_port_id(decoded)
        switch_id = _extract_switch_id(decoded)
        switch_info = _extract_hostname(decoded)
        if port_id and switch_id and switch_info:
            return {"port_id": port_id, "switch_id": switch_id, "switch_info": switch_info}
        LOG.warning("Failed to extract local_link_info from LLDP data for %s", node_id)
    except (binascii.Error, core.MappingError, netaddr.AddrFormatError) as e:
        LOG.warning("Failed to parse lldp_raw data for Node %s: %s", node_id, e)
    return {}


def _extract_port_id(data: dict) -> str | None:
    for value in data.get(lldp_tlvs.LLDP_TLV_PORT_ID, []):
        parsed = lldp_tlvs.PortId.parse(value)
        if parsed.value:  # pyright: ignore reportAttributeAccessIssue
            return parsed.value.value  # pyright: ignore reportAttributeAccessIssue


def _extract_switch_id(data: dict) -> str | None:
    for value in data.get(lldp_tlvs.LLDP_TLV_CHASSIS_ID, []):
        parsed = lldp_tlvs.ChassisId.parse(value)
        if "mac_address" in parsed.subtype:  # pyright: ignore reportAttributeAccessIssue
            return str(parsed.value.value)  # pyright: ignore reportAttributeAccessIssue


def _extract_hostname(data: dict) -> str | None:
    for value in data.get(lldp_tlvs.LLDP_TLV_SYS_NAME, []):
        parsed = lldp_tlvs.SysName.parse(value)
        if parsed.value:  # pyright: ignore reportAttributeAccessIssue
            return parsed.value  # pyright: ignore reportAttributeAccessIssue


def vlan_group_name(local_link_connection) -> str | None:
    switch_name = local_link_connection.get("switch_info")
    if not switch_name:
        return

    return ironic_understack.vlan_group_name_convention.vlan_group_name(switch_name)


def _update_port_physical_network(port, new_physical_network: str|None):
    old_physical_network = port.physical_network

    if new_physical_network == old_physical_network:
        return

    LOG.debug(
        "Updating port %s physical_network from %s to %s",
        port.id,
        old_physical_network,
        new_physical_network,
    )
    port.physical_network = new_physical_network
    port.save()


def _update_node_traits(task, vlan_groups: set[str]):
    """Add or remove traits to the node.

    We manage one trait: "CUSTOM_STORAGE_SWITCH" which is added if the node has
    any ports connected to a storage fabric, othwise it is removed from the
    node.
    """
    TRAIT_STORAGE_SWITCH = "CUSTOM_STORAGE_SWITCH"

    storage_vlan_groups = {
        x for x in vlan_groups if x.endswith("-storage")
    }

    if storage_vlan_groups:
        task.node.add_trait(TRAIT_STORAGE_SWITCH)
    else:
        try:
            task.node.remove_trait(TRAIT_STORAGE_SWITCH)
        except openstack.exceptions.NotFoundException:
            pass

    task.node.save()
