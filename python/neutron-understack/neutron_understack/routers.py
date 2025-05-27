import logging
from uuid import UUID

from neutron.common.ovn import constants as ovn_const
from neutron.common.ovn import utils as ovn_utils
from neutron.conf.agent import ovs_conf
from neutron.objects import base as base_obj
from neutron.objects.network import NetworkSegment
from neutron.plugins.ml2 import db as ml2_db
from neutron_lib import constants as p_const
from neutron_lib import context as n_context
from neutron_lib.api.definitions import segment as segment_def
from neutron_lib.plugins import directory
from oslo_config import cfg

from neutron_understack import utils

from .ml2_type_annotations import PortContext

LOG = logging.getLogger(__name__)


def create_port_postcommit(context: PortContext, driver):
    """Handles `create_port_postcommit` event for Router ports."""
    port_id = context.current["id"]
    device_id = context.current["device_id"]
    device_owner = context.current["device_owner"]

    segment = _existing_segment(context) or create_router_segment(driver, context)

    # Trunk plugin does not allow the subport have a device_id set when it is
    # added to a trunk, so we temporarily clear the device_id and restore it
    # after it's added.
    utils.clear_device_id_for_port(port_id)
    add_subport_to_trunk(context, segment)
    utils.set_device_id_and_owner_for_port(
        port_id=port_id,
        device_id=device_id,
        device_owner=device_owner,
    )


def _existing_segment(context):
    filter = {
        "network_id": context.current["network_id"],
        "network_type": p_const.TYPE_VLAN,
        "physical_network": cfg.CONF.ml2_understack.network_node_switchport_physnet,
    }
    admin_context = n_context.get_admin_context()
    matching_segments = NetworkSegment.get_objects(
        admin_context, _pager=base_obj.Pager(limit=1), **filter
    )
    if matching_segments:
        return matching_segments[0]
    else:
        return None


def add_subport_to_trunk(context, segment):
    """Adds requested port as a subport of a trunk connection for network nodes.

    The trunk and parent port must already exist.
    """
    port_id = context.current["id"]
    trunk_id = cfg.CONF.ml2_understack.network_node_trunk_uuid
    subports = {
        "sub_ports": [
            {
                "port_id": port_id,
                "segmentation_id": segment["segmentation_id"],
                "segmentation_type": p_const.TYPE_VLAN,
            },
        ]
    }
    LOG.debug("router subports to be added %(subports)s", {"subports": subports})
    trunk_plugin = utils.fetch_trunk_plugin()
    LOG.debug("trunk plugin: %(plugin)s", {"plugin": trunk_plugin})
    trunk_plugin.add_subports(
        context=context.plugin_context,
        trunk_id=trunk_id,
        subports=subports,
    )


def create_router_segment(driver, context: PortContext):
    """Creates a dynamic segment for connection between the router and network node."""
    network_id = UUID(context.current["network_id"])
    physnet = cfg.CONF.ml2_understack.network_node_switchport_physnet
    if not physnet:
        raise ValueError(
            "please configure ml2_understack.network_node_switchport_physnet"
        )
    segment = utils.allocate_dynamic_segment(
        network_id=str(network_id),
        physnet=physnet,
    )
    segment_obj = utils.network_segment_by_id(segment["id"])
    create_uplink_port(segment_obj, str(network_id))

    LOG.debug("router dynamic segment: %(segment)s", {"segment": segment})
    return segment


_cached_ovn_client = None


def ovn_client():
    """Retrieve the OVN client from the OVN ML2 plugin."""
    global _cached_ovn_client
    if _cached_ovn_client:
        return _cached_ovn_client

    ml2_plugin = directory.get_plugin()
    if not ml2_plugin:
        return None

    plugin = None
    for driver in ml2_plugin.mechanism_manager.ordered_mech_drivers:
        if driver.name == "ovn":
            plugin = driver.obj
    ovn_plugin = next(
        (
            driver.obj
            for driver in ml2_plugin.mechanism_manager.ordered_mech_drivers
            if driver.name == "ovn"
        ),
        None,
    )
    if ovn_plugin is None:
        raise Exception("No OVN Plugin available")

    _cached_ovn_client = plugin._ovn_client
    return _cached_ovn_client


def create_uplink_port(segment: NetworkSegment, network_id: str, txn=None):
    """Create a localnet port to connect given NetworkSegment to a network node."""
    tag = segment.get(segment_def.SEGMENTATION_ID, [])
    physnet = segment.get(segment_def.PHYSICAL_NETWORK)
    fdb_enabled = "true"
    options = {
        "network_name": physnet,
        ovn_const.LSP_OPTIONS_MCAST_FLOOD_REPORTS: ovs_conf.get_igmp_flood_reports(),
        ovn_const.LSP_OPTIONS_MCAST_FLOOD: ovs_conf.get_igmp_flood(),
        ovn_const.LSP_OPTIONS_LOCALNET_LEARN_FDB: fdb_enabled,
    }
    cmd = ovn_client()._nb_idl.create_lswitch_port(
        lport_name=f"uplink-{segment['id']}",
        lswitch_name=ovn_utils.ovn_name(network_id),
        addresses=[ovn_const.UNKNOWN_ADDR],
        external_ids={},
        type=ovn_const.LSP_TYPE_LOCALNET,
        tag=tag,
        options=options,
    )
    ovn_client()._transaction([cmd], txn=txn)


def delete_uplink_port(segment: NetworkSegment, network_id: str):
    """Remove a localnet uplink port from a network node."""
    port_to_del = f"uplink-{segment['id']}"
    cmd = ovn_client()._nb_idl.delete_lswitch_port(
        lport_name=port_to_del, lswitch_name=ovn_utils.ovn_name(network_id)
    )
    return ovn_client()._transaction([cmd])


def handle_router_interface_removal(_resource, _event, trigger, payload) -> None:
    """Handles the removal of a router interface.

    When router interface port is deleted, we remove the corresponding subport
    from the trunk and delete OVN localnet port.
    """
    port = payload.metadata["port"]
    if port["device_owner"] in [p_const.DEVICE_OWNER_ROUTER_INTF]:
        _handle_localnet_port_removal(port)
        _handle_subport_removal(port)


def _handle_localnet_port_removal(port):
    """Removes OVN localnet port that is used for this trunked VLAN."""
    admin_context = n_context.get_admin_context()
    try:
        parent_port_id = port["binding:profile"]["parent_name"]
    except KeyError as err:
        LOG.error(
            "Port %(port)s is not added to a trunk. %(err)",
            {"port": port["id"], "err": err},
        )
        return

    parent_port = utils.fetch_port_object(parent_port_id)
    binding_host = parent_port.bindings[0].host

    binding_levels = ml2_db.get_binding_level_objs(
        admin_context, port["id"], binding_host
    )

    LOG.debug("binding_levels: %(lvls)s", {"lvls": binding_levels})

    if binding_levels:
        segment_id = binding_levels[-1].segment_id
        LOG.debug("looking up segment_id: %s", segment_id)
        segment_obj = utils.network_segment_by_id(segment_id)
        # ovn_client().delete_provnet_port(port["network_id"], segment_obj)
        delete_uplink_port(segment_obj, port["network_id"])


def _handle_subport_removal(port):
    """Removes router's subport from a network node trunk."""
    # trunk_id will be discovered dynamically at some point
    trunk_id = cfg.CONF.ml2_understack.network_node_trunk_uuid
    LOG.debug("Router, Removing subport: %s(port)s", {"port": port})
    port_id = port["id"]
    try:
        utils.remove_subport_from_trunk(trunk_id, port_id)
    except Exception as err:
        LOG.error("failed removing_subport: %(error)s", {"error": err})
