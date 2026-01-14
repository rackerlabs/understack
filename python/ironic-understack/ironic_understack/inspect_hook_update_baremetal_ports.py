import re
from typing import Any

from ironic import objects
from ironic.common import exception
from ironic.drivers.modules.inspector.hooks import base
from oslo_log import log as logging

import ironic_understack.vlan_group_name_convention
from ironic_understack.conf import CONF
from ironic_understack.inspected_port import InspectedPort
from ironic_understack.ironic_wrapper import ironic_ports_for_node

LOG = logging.getLogger(__name__)


class InspectHookUpdateBaremetalPorts(base.InspectionHook):
    """Hook to update ports according to LLDP data."""

    # "validate-interfaces" provides the all_interfaces field in plugin_data.
    # "parse-lldp" provides the parsed_lldp field in plugin_data.
    dependencies = ["validate-interfaces", "parse-lldp"]

    def __call__(self, task, inventory, plugin_data):
        """Update Ports' local_link_info and physnet based on LLDP data.

        Using the parsed_lldp data as discovered by inspection, validate the
        topology and determine the local_link_connection and vlan group names
        for each of our connections.

        The ports plugin has already created/deleted the ports as appropriate
        and set their "pxe" flag.

        We update attributes of all baremetal ports for this node:

        - local_link_info.port_id (e.g. "Ethernet1/1")
        - local_link_info.switch_id (e.g. "aa:bb:cc:dd:ee:ff")
        - local_link_info.switch_info (e.g. "a1-1-1.ord1.rackspace.net")
        - physical_network (e.g. "a1-1-network")

        We also add or remove node "traits" based on the inventory data.  We
        control the trait "CUSTOM_STORAGE_SWITCH".
        """
        node_uuid: str = task.node.uuid

        inspected_ports = _parse_plugin_data(plugin_data)
        if not inspected_ports:
            LOG.error("No LLDP data for node %s", node_uuid)
            return

        ports_by_mac = {p.mac_address: p for p in inspected_ports}

        vlan_groups = ironic_understack.vlan_group_name_convention.vlan_group_names(
            inspected_ports,
            CONF.ironic_understack.switch_name_vlan_group_mapping,
        )
        LOG.debug(
            "Node=%(node)s vlan_groups=%(groups)s",
            {"node": node_uuid, "groups": vlan_groups},
        )

        _update_port_attrs(task, ports_by_mac, vlan_groups, node_uuid)
        _set_node_traits(task, {x for x in vlan_groups.values() if x})


def _parse_plugin_data(plugin_data: dict) -> list[InspectedPort]:
    mac = {
        interface["name"]: interface["mac_address"]
        for interface in plugin_data["all_interfaces"].values()
    }

    return [
        InspectedPort(
            mac_address=mac[name],
            name=name,
            switch_system_name=_normalise_switch_name(lldp["switch_system_name"]),
            switch_chassis_id=str(lldp["switch_chassis_id"]).lower(),
            switch_port_id=str(lldp["switch_port_id"]),
        )
        for name, lldp in plugin_data["parsed_lldp"].items()
    ]


def _normalise_switch_name(name: str) -> str:
    suffix = ".rackspace.net"
    name = str(name).lower()
    name = name if name.endswith(suffix) else name + suffix
    return name


def _update_port_attrs(task, ports_by_mac, vlan_groups, node_uuid):
    for baremetal_port in ironic_ports_for_node(task.context, task.node.id):
        inspected_port = ports_by_mac.get(baremetal_port.address)
        if inspected_port:
            vlan_group = vlan_groups.get(inspected_port.switch_system_name)
            LOG.info(
                "Port=%(uuid)s Node=%(node)s is connected %(lldp)s, %(vlan_group)s",
                {
                    "uuid": baremetal_port.uuid,
                    "node": node_uuid,
                    "lldp": inspected_port,
                    "vlan_group": vlan_group,
                },
            )
            _set_port_attributes(baremetal_port, node_uuid, inspected_port, vlan_group)
        else:
            LOG.info(
                "Port=%(uuid)s Node=%(node)s has no LLDP connection",
                {"uuid": baremetal_port.uuid, "node": node_uuid},
            )
            _clear_port_attributes(baremetal_port, node_uuid)


def _set_port_attributes(
    port: Any,
    node_uuid: str,
    inspected_port: InspectedPort,
    physical_network: str | None,
):
    category = None
    if physical_network:
        category = physical_network.split("-")[-1]

    try:
        if port.local_link_connection != inspected_port.local_link_connection:
            LOG.debug(
                "Updating node %s port %s local_link_connection %s => %s",
                node_uuid,
                port.uuid,
                port.local_link_connection,
                inspected_port.local_link_connection,
            )
            port.local_link_connection = inspected_port.local_link_connection

        if physical_network and not physical_network.endswith("-network"):
            physical_network = None
            category = "storage"

        if port.physical_network != physical_network:
            LOG.debug(
                "Updating node %s port %s physical_network from %s to %s",
                node_uuid,
                port.id,
                port.physical_network,
                physical_network,
            )
            port.physical_network = physical_network

        if port.category != category:
            port.category = category

        port.save()
    except exception.IronicException as e:
        LOG.warning(
            "Failed to update port %(uuid)s for node %(node)s. Error: %(error)s",
            {"uuid": port.id, "node": node_uuid, "error": e},
        )


def _clear_port_attributes(port: Any, node_uuid: str):
    try:
        port.local_link_connection = {}
        port.physical_network = None
        port.category = None
        port.save()
    except exception.IronicException as e:
        LOG.warning(
            "Failed to clear port %(uuid)s for node %(node)s. Error: %(error)s",
            {"uuid": port.id, "node": node_uuid, "error": e},
        )


def _set_node_traits(task, vlan_groups: set[str]):
    """Add or remove traits to the node.

    We manage a traits for each type of VLAN Group that can be connected to a
    node.

    For example, a connection to VLAN Group whose name ends in "-storage" will
    result in a trait being added to the node called "CUSTOM_STORAGE_SWITCH".

    We remove pre-existing traits if the node does not have the required
    connections.

    Traits other than CUSTOM_*_SWITCH are left alone.
    """
    node = task.node
    existing_traits = set(node.traits.get_trait_names())
    vlan_group_traits = {_trait_name(x) for x in vlan_groups if x}
    irrelevant_existing_traits = {x for x in existing_traits if not _is_our_trait(x)}
    required_traits = irrelevant_existing_traits.union(vlan_group_traits)

    if existing_traits == required_traits:
        LOG.debug(
            "Node %s traits %s are all present and correct",
            node.uuid,
            vlan_group_traits,
        )
    else:
        LOG.info(
            "Updating traits for node %s from %s to %s",
            node.uuid,
            existing_traits,
            required_traits,
        )
        objects.TraitList.create(task.context, task.node.id, required_traits)
        node.save()


def _trait_name(vlan_group_name: str) -> str:
    suffix = vlan_group_name.upper().split("-")[-1]
    return f"CUSTOM_{suffix}_SWITCH"


def _is_our_trait(name: str) -> bool:
    return bool(re.match(r"^CUSTOM_[A-Z0-9]+_SWITCH$", name))
