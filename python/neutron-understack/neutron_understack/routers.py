import logging

from neutron.common.ovn import constants as ovn_const
from neutron.common.ovn import utils as ovn_utils
from neutron.conf.agent import ovs_conf
from neutron.objects.network import NetworkSegment
from neutron.objects.ports import Port
from neutron.plugins.ml2.drivers.ovn.mech_driver.ovsdb.ovn_client import OVNClient
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
    p_const.DEVICE_OWNER_ROUTER_INTF,
    p_const.DEVICE_OWNER_ROUTER_GW,
]


def create_port_postcommit(context: PortContext) -> None:
    """Router port creation logic.

    When router port is created, we can end up in one of two situations:

    1. It's a first router port using the network
    2. There are already other routers that use this network

    In situation 1, we have to:
    - create or find the dynamic network segment for network node
    - create a segment-shared Neutron port that has network_id same as
      router-specific port. Set the name to help identification.
    - add the segment-shared port to a network node trunk
    - create localnet port in OVN

    In situation 2, we don't have to do anything.
    """
    network_id = context.current["network_id"]
    if not is_only_router_port_on_network(
        network_id=network_id, transaction_context=context.plugin_context
    ):
        LOG.debug(
            "Creating only a router port %(port)s for a network %(network)s "
            "as there are already other routers on the same network.",
            {"port": context.current["id"], "network": network_id},
        )
        return

    segment = fetch_or_create_router_segment(context)

    # Trunk
    shared_port = utils.create_neutron_port_for_segment(segment, context)
    add_subport_to_trunk(shared_port, segment, context)

    # OVN
    segment_obj = utils.network_segment_by_id(segment["id"])
    create_uplink_port(segment_obj, network_id)


def is_only_router_port_on_network(
    network_id: str,
    transaction_context: n_context.Context | None = None,
) -> bool:
    transaction_context = transaction_context or n_context.get_admin_context()

    other_router_ports = Port.get_objects(
        transaction_context,
        network_id=network_id,
        device_owner=ROUTER_INTERFACE_AND_GW,
    )

    LOG.debug("Router ports found: %(ports)s", {"ports": other_router_ports})
    if len(other_router_ports) > 1:
        return False
    else:
        return True


def add_subport_to_trunk(
    shared_port: PortDict, segment: NetworkSegmentDict, context: PortContext
) -> None:
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
    utils.fetch_trunk_plugin().add_subports(
        context=context.plugin_context,
        trunk_id=cfg.CONF.ml2_understack.network_node_trunk_uuid,
        subports=subports,
    )


def fetch_or_create_router_segment(context: PortContext) -> NetworkSegmentDict:
    """Get or create a dynamic segment.

    allocate_dynamic_segment will get or create a segment for connection between
    the router and network node.
    """
    network_id = context.current["network_id"]
    physnet = cfg.CONF.ml2_understack.network_node_switchport_physnet
    if not physnet:
        raise ValueError(
            "please configure ml2_understack.network_node_switchport_physnet"
        )
    segment = utils.allocate_dynamic_segment(
        network_id=network_id,
        physnet=physnet,
    )
    if not segment:
        raise Exception(
            "failed allocating dynamic segment for"
            "network_id=%(network_id)s physnet=%(physnet)s",
            {"network_id": network_id, "physnet": physnet},
        )
    LOG.debug("router dynamic segment: %(segment)s", {"segment": segment})
    return segment


_cached_ovn_client = None


def ovn_client() -> OVNClient | None:
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


def create_uplink_port(segment: NetworkSegment, network_id: str, txn=None) -> None:
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


def delete_uplink_port(segment: NetworkSegment, network_id: str) -> None:
    """Remove a localnet uplink port from a network node."""
    port_to_del = f"uplink-{segment['id']}"
    cmd = ovn_client()._nb_idl.delete_lswitch_port(
        lport_name=port_to_del, lswitch_name=ovn_utils.ovn_name(network_id)
    )
    ovn_client()._transaction([cmd])


def handle_router_interface_removal(_resource, _event, trigger, payload) -> None:
    """Handles the removal of a router interface.

    When router interface port is deleted, we remove the corresponding subport
    from the trunk and delete OVN localnet port.

    We have router-specific port that is being deleted.
    We have segment-shared port for shared networks.

    When the delete router port event is received, we can be in two situations:
    1. The port is the last one that uses shared network.
    2. The port is being detached from a network, but there are other routers
       still using that network.

    In situation 1, we have to:
    - identify segment-shared Neutron port. This is done by looking up
      ports by name in format uplink-<segment_id>.
    - remove the segment-shared Neutron port from a trunk
    - remove the localnet port in OVN for same segmentation_id/VLAN
    - delete the segment-shared Neutron port

    In situation 2, we don't have to do anything. Router-specific port gets
    deleted by Neutron and segment-shared port stays around.
    """
    port = payload.metadata["port"]
    network_id = port["network_id"]

    if port["device_owner"] not in ROUTER_INTERFACE_AND_GW:
        return

    if not is_only_router_port_on_network(network_id):
        LOG.debug(
            "Deleting only Router port %(port)s as there are other"
            " router ports using the same network",
            {"port": port},
        )
        return

    segment = fetch_router_network_segment(network_id)
    if not segment:
        return

    shared_port = fetch_shared_router_port(segment)
    if not shared_port:
        return

    handle_subport_removal(shared_port)
    delete_uplink_port(segment, network_id)
    shared_port.delete()


def handle_subport_removal(port: Port) -> None:
    """Removes router's subport from a network node trunk."""
    # trunk_id will be discovered dynamically at some point
    trunk_id = cfg.CONF.ml2_understack.network_node_trunk_uuid
    LOG.debug("Router, Removing subport: %s(port)s", {"port": port})
    port_id = port["id"]
    try:
        utils.remove_subport_from_trunk(trunk_id, port_id)
    except Exception as err:
        LOG.error("failed removing_subport: %(error)s", {"error": err})


def fetch_router_network_segment(network_id: str) -> NetworkSegment | None:
    segment = utils.network_segment_by_physnet(
        network_id, cfg.CONF.ml2_understack.network_node_switchport_physnet
    )
    if not segment:
        LOG.error(
            "Router network segment not found for network %(network_id)s",
            {"network_id": network_id},
        )
        return
    LOG.debug("Router network segment found %(segment)s", {"segment": segment})
    return segment


def fetch_shared_router_port(segment: NetworkSegment) -> Port | None:
    shared_ports = Port.get_objects(
        n_context.get_admin_context(), name=f"uplink-{segment['id']}"
    )

    if not shared_ports:
        LOG.error(
            "No router shared ports found for segment %(segment)s", {"segment", segment}
        )
        return
    LOG.debug("Router shared ports found %(ports)s", {"ports": shared_ports})
    return shared_ports[0]
