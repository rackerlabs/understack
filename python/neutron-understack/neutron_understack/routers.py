import logging
from typing import cast
from uuid import UUID

from neutron.common.ovn import constants as ovn_const
from neutron.common.ovn import utils as ovn_utils
from neutron.conf.agent import ovs_conf
from neutron.objects import base as base_obj
from neutron.objects.network import NetworkSegment
from neutron.objects.ports import Port
from neutron.plugins.ml2 import db as ml2_db
from neutron_lib import constants as p_const
from neutron_lib import context as n_context
from neutron_lib.api.definitions import segment as segment_def
from neutron_lib.plugins import directory
from oslo_config import cfg

from neutron_understack import utils

from .ml2_type_annotations import NetworkSegmentDict
from .ml2_type_annotations import PortContext
from .ml2_type_annotations import PortDict

LOG = logging.getLogger(__name__)

ROUTER_INTERFACE_AND_GW = [
    p_const.DEVICE_OWNER_ROUTER_INTF, p_const.DEVICE_OWNER_ROUTER_GW
]


def create_port_postcommit(context: PortContext):
    # When router port is created, we can end up in one of two situations:
    # 1. It's a first router port using the network
    # 2. There are already other routers that use this network
    #
    # In situation 1, we have to:
    # - create or find the dynamic network segment for network node
    # - create a segment-shared Neutron port that has network_id same as
    #   router-specific port. Set the name to help identification.
    # - add the segment-shared port to a network node trunk
    # - create localnet port in OVN
    #
    # In situation 2, we don't have to do anything.
    if not is_first_port_on_network(context):
        LOG.debug(
            "Creating a router port for a network that already has other routers."
        )
        return

    segment = _existing_segment(context) or create_router_segment(context)
    network_id = context.current["network_id"]

    # Trunk
    shared_port = utils.create_neutron_port_for_segment(segment, context)
    add_subport_to_trunk(shared_port, segment, context)

    # OVN
    segment_obj = utils.network_segment_by_id(segment["id"])
    create_uplink_port(segment_obj, str(network_id))


def is_first_port_on_network(context: PortContext) -> bool:
    network_id = context.current["network_id"]

    other_router_ports = Port.get_objects(
        context.plugin_context,
        network_id=network_id,
        device_owner=[
            p_const.DEVICE_OWNER_ROUTER_INTF,
            p_const.DEVICE_OWNER_ROUTER_GW,
        ],
    )

    LOG.debug("Router ports found: %(ports)s", {"ports": other_router_ports})
    if len(other_router_ports) > 1:
        return False
    else:
        return True


def _existing_segment(context) -> NetworkSegmentDict | None:
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
        return cast(NetworkSegmentDict, matching_segments[0].to_dict())
    else:
        return None


def add_subport_to_trunk(
    shared_port: PortDict, segment: NetworkSegmentDict, context: PortContext
):
    """Adds requested port as a subport of a trunk connection for network nodes.

    The trunk and parent port must already exist.
    """
    subports = {
        "sub_ports": [
            {
                "port_id": shared_port["id"],
                "segmentation_id": segment["segmentation_id"],
                "segmentation_type": p_const.TYPE_VLAN,
            },
        ]
    }
    return utils.fetch_trunk_plugin().add_subports(
        context=context.plugin_context,
        trunk_id=cfg.CONF.ml2_understack.network_node_trunk_uuid,
        subports=subports,
    )


def create_router_segment(context: PortContext) -> NetworkSegmentDict:
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
    if not segment:
        raise Exception(
            "failed allocating dynamic segment for"
            "network_id=%(network_id)s physnet=%(physnet)s",
            {"network_id": str(network_id), "physnet": physnet},
        )
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
    # We have router-specific port that is being deleted.
    # We have segment-shared port for shared networks.
    #
    # When the delete router port event is received, we can be in two situations:
    # 1. The port is the last one that uses shared network.
    # 2. The port is being detached from a network, but there are other routers
    #    still using that network.
    #
    # In situation 1, we have to:
    # - identify segment-shared Neutron port. This can be done by looking up
    #   ports that are subports of the preconfigured "network node" trunk with
    #   matching segmentation_id and network_id.
    # - remove the segment-shared Neutron port from a trunk
    # - remove the localnet port in OVN for same segmentation_id/VLAN
    # - delete the segment-shared Neutron port
    #
    # In situation 2, we don't have to do nothing. Router-specific port gets
    # deleted by Neutron and segment-shared port stays around.

    port = payload.metadata["port"]

    if port["device_owner"] not in ROUTER_INTERFACE_AND_GW:
        return

    if not is_last_port_on_network(port):
        LOG.debug(
            "Deleting only Router port %(port)s as there are other"
            " router ports using the same network", {"port": port}
        )
        return

    network_id = port["network_id"]

    segment = utils.network_segment_by_physnet(
        network_id,
        cfg.CONF.ml2_understack.network_node_switchport_physnet
    )
    if not segment:
        LOG.error(
            "Router network segment not found for network %(network_id)s",
            {"network_id": network_id}
        )
        return

    LOG.debug("Router network segment found %(segment)s", {"segment": segment})
    shared_ports = Port.get_objects(
        n_context.get_admin_context(),
        name=f"uplink-{segment['id']}"
    )

    if not shared_ports:
        LOG.error(
            "No router shared ports found for segment %(segment)s",
            {"segment", segment}
        )
        return
    LOG.debug("Router shared ports found %(ports)s", {"ports": shared_ports})

    shared_port = shared_ports[0]

    _handle_subport_removal(shared_port)
    delete_uplink_port(segment, network_id)
    shared_port.delete()


def is_last_port_on_network(port: PortDict) -> bool:
    network_id = port["network_id"]

    other_router_ports = Port.get_objects(
        n_context.get_admin_context(),
        network_id=network_id,
        device_owner=ROUTER_INTERFACE_AND_GW,
    )

    LOG.debug("Router ports found: %(ports)s", {"ports": other_router_ports})
    if len(other_router_ports) > 1:
        return False
    else:
        return True


# def _handle_localnet_port_removal(port):
#     """Removes OVN localnet port that is used for this trunked VLAN."""
#     admin_context = n_context.get_admin_context()
#     try:
#         parent_port_id = port["binding:profile"]["parent_name"]
#     except KeyError as err:
#         LOG.error(
#             "Port %(port)s is not added to a trunk. %(err)",
#             {"port": port["id"], "err": err},
#         )
#         return

#     parent_port = utils.fetch_port_object(parent_port_id)
#     binding_host = parent_port.bindings[0].host

#     binding_levels = ml2_db.get_binding_level_objs(
#         admin_context, port["id"], binding_host
#     )

#     LOG.debug("binding_levels: %(lvls)s", {"lvls": binding_levels})

#     if binding_levels:
#         segment_id = binding_levels[-1].segment_id
#         LOG.debug("looking up segment_id: %s", segment_id)
#         segment_obj = utils.network_segment_by_id(segment_id)
#         # ovn_client().delete_provnet_port(port["network_id"], segment_obj)
#         delete_uplink_port(segment_obj, port["network_id"])


def _handle_subport_removal(port: Port):
    """Removes router's subport from a network node trunk."""
    # trunk_id will be discovered dynamically at some point
    trunk_id = cfg.CONF.ml2_understack.network_node_trunk_uuid
    LOG.debug("Router, Removing subport: %s(port)s", {"port": port})
    port_id = port["id"]
    try:
        utils.remove_subport_from_trunk(trunk_id, port_id)
    except Exception as err:
        LOG.error("failed removing_subport: %(error)s", {"error": err})
