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
    port_id = context.current["id"]
    router_id = context.current.get("device_id")

    if not is_only_router_port_on_network(
        network_id=network_id, transaction_context=context.plugin_context
    ):
        LOG.info(
            "Router port %(port)s on router %(router)s: network %(network)s "
            "already has another router interface — VLAN infrastructure already "
            "exists, nothing to do",
            {"port": port_id, "router": router_id, "network": network_id},
        )
        return

    LOG.info(
        "Router port %(port)s on router %(router)s: first router on network "
        "%(network)s — starting VLAN/trunk/OVN setup",
        {"port": port_id, "router": router_id, "network": network_id},
    )

    # Step 1: allocate dynamic VLAN segment for the network node physnet
    LOG.debug(
        "Step 1: allocating dynamic VLAN segment for network %(net)s",
        {"net": network_id},
    )
    segment = fetch_or_create_router_segment(context)
    LOG.info(
        "Step 1 done: dynamic segment %(seg)s VLAN %(vlan)s allocated for "
        "network %(net)s",
        {
            "seg": segment["id"],
            "vlan": segment.get("segmentation_id"),
            "net": network_id,
        },
    )

    # Step 2: create shared Neutron port on the network node for this VLAN
    LOG.debug(
        "Step 2: creating shared Neutron port for segment %(seg)s",
        {"seg": segment["id"]},
    )
    shared_port = utils.create_neutron_port_for_segment(segment, context)
    LOG.info(
        "Step 2 done: shared Neutron port %(port)s created on network %(network)s",
        {"port": shared_port["id"], "network": network_id},
    )

    # Step 3: add the shared port as a subport on the network node trunk
    LOG.debug(
        "Step 3: adding port %(port)s as subport (VLAN %(vlan)s) to network node trunk",
        {"port": shared_port["id"], "vlan": segment.get("segmentation_id")},
    )
    add_subport_to_trunk(shared_port, segment)
    LOG.info("Step 3 done: subport added to trunk")

    # Step 4: create OVN localnet port to wire OVN to the physical VLAN
    segment_obj = utils.network_segment_by_id(segment["id"])
    LOG.debug(
        "Step 4: creating OVN localnet port uplink-%(seg)s for network %(net)s",
        {"seg": segment["id"], "net": network_id},
    )
    create_uplink_port(segment_obj, network_id)
    LOG.info(
        "Step 4 done: OVN localnet port uplink-%(seg)s created for router "
        "%(router)s — network=%(network)s shared_port=%(port)s vlan=%(vlan)s. "
        "Undersync will push SVI config to physical switch",
        {
            "seg": segment["id"],
            "router": router_id,
            "network": network_id,
            "port": shared_port["id"],
            "vlan": segment.get("segmentation_id"),
        },
    )


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

    router_port_ids = [getattr(port, "id", None) for port in other_router_ports]
    LOG.info(
        "Router-owned ports on network %(network)s: count=%(count)d ids=%(ports)s",
        {
            "network": network_id,
            "count": len(other_router_ports),
            "ports": router_port_ids,
        },
    )
    return not len(other_router_ports) > 1


def add_subport_to_trunk(shared_port: PortDict, segment: NetworkSegmentDict) -> None:
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
    try:
        trunk_id = utils.fetch_network_node_trunk_id()
    except Exception:
        LOG.exception(
            "add_subport_to_trunk: failed to find network node trunk for "
            "shared port %(port)s VLAN %(vlan)s",
            {
                "port": shared_port["id"],
                "vlan": segment["segmentation_id"],
            },
        )
        raise

    LOG.debug(
        "add_subport_to_trunk: trunk %(trunk)s port %(port)s VLAN %(vlan)s",
        {
            "trunk": trunk_id,
            "port": shared_port["id"],
            "vlan": segment["segmentation_id"],
        },
    )
    try:
        utils.fetch_trunk_plugin().add_subports(
            context=n_context.get_admin_context(),
            trunk_id=trunk_id,
            subports=subports,
        )
    except Exception:
        LOG.exception(
            "add_subport_to_trunk: failed adding shared port %(port)s as "
            "VLAN %(vlan)s subport to trunk %(trunk)s",
            {
                "port": shared_port["id"],
                "vlan": segment["segmentation_id"],
                "trunk": trunk_id,
            },
        )
        raise


def fetch_or_create_router_segment(context: PortContext) -> NetworkSegmentDict:
    """Get or create a dynamic segment.

    allocate_dynamic_segment will get or create a segment for connection between
    the router and network node.
    """
    network_id = context.current["network_id"]
    physnet = cfg.CONF.ml2_understack.network_node_switchport_physnet
    if not physnet:
        LOG.error(
            "Router dynamic segment allocation failed for network %(network)s: "
            "ml2_understack.network_node_switchport_physnet is not configured",
            {"network": network_id},
        )
        raise ValueError(
            "please configure ml2_understack.network_node_switchport_physnet"
        )
    LOG.info(
        "Fetching or allocating router dynamic segment: network=%(network)s "
        "physnet=%(physnet)s",
        {"network": network_id, "physnet": physnet},
    )
    segment = utils.allocate_dynamic_segment(
        network_id=network_id,
        physnet=physnet,
    )
    if not segment:
        LOG.error(
            "Router dynamic segment allocation returned no segment: "
            "network=%(network)s physnet=%(physnet)s",
            {"network": network_id, "physnet": physnet},
        )
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
    global _cached_ovn_client  # noqa: PLW0603
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
    port_name = f"uplink-{segment['id']}"
    LOG.info(
        "Creating OVN localnet port %(port)s: network=%(network)s "
        "physnet=%(physnet)s vlan=%(vlan)s options=%(options)s",
        {
            "port": port_name,
            "network": network_id,
            "physnet": physnet,
            "vlan": tag,
            "options": options,
        },
    )
    client = ovn_client()
    cmd = client._nb_idl.create_lswitch_port(
        lport_name=port_name,
        lswitch_name=ovn_utils.ovn_name(network_id),
        addresses=[ovn_const.UNKNOWN_ADDR],
        external_ids={},
        type=ovn_const.LSP_TYPE_LOCALNET,
        tag=tag,
        options=options,
    )
    try:
        client._transaction([cmd], txn=txn)
    except Exception:
        LOG.exception(
            "Failed creating OVN localnet port %(port)s: network=%(network)s "
            "physnet=%(physnet)s vlan=%(vlan)s",
            {
                "port": port_name,
                "network": network_id,
                "physnet": physnet,
                "vlan": tag,
            },
        )
        raise


def link_vxlan_network_ha_chassis_group(_resource, _event, _trigger, payload) -> None:
    """Populate the unified network HCG (and anchor the internal LRP) for vxlan.

    Workaround for a neutron bug exposed in 2026.1. For a router with a vxlan-type
    external gateway, neutron pins the Logical_Router to a single
    chassis via ``options:chassis`` and creates a per-router HA_Chassis_Group
    (neutron-<router_id>) carrying that chassis, but it never sets
    ha_chassis_group on the gateway LRP. neutron's link_network_ha_chassis_group
    (fired when the internal LRP is created) bails out at its
    ``if not gw_lrps[0].ha_chassis_group`` check, so it never copies the chassis
    into the per-network unified HCG (neutron-<network_id>). External/baremetal
    ports on that network reference the empty network HCG, so no chassis owns
    them and routing/ARP breaks.

    We do what link_network_ha_chassis_group would have done, but source the
    chassis from the router HCG instead of the (empty) gateway LRP: populate the
    unified network HCG with sync_ha_chassis_group_network_unified, then anchor
    the internal router-interface LRP to that same HCG. External ports already
    reference the unified network HCG, so populating it fixes them.

    Subscribed to ROUTER_INTERFACE/AFTER_CREATE at a priority that runs after
    neutron's OVN handler, so the LRP (lrp-<port_id>) already exists by now.
    """
    router_id = payload.states[0].id
    port = payload.metadata["port"]
    port_id = port["id"]
    network_id = port["network_id"]

    try:
        client = ovn_client()
        if not client:
            return
        nb_idl = client._nb_idl

        # Vxlan-gateway signal: the per-router HCG exists with chassis.
        # VLAN/FLAT gateways have no router HCG and are handled by neutron.
        router_hcg = nb_idl.lookup(
            "HA_Chassis_Group", ovn_utils.ovn_name(router_id), default=None
        )
        if not router_hcg or not router_hcg.ha_chassis:
            LOG.debug(
                "No HA_Chassis_Group with chassis found for router %(router)s",
                {"router": router_id},
            )
            return

        chassis_prio = {hc.chassis_name: hc.priority for hc in router_hcg.ha_chassis}
        lrp_name = ovn_utils.ovn_lrouter_port_name(port_id)

        LOG.info(
            "Linking unified HCG for network %(net)s (router %(router)s) with "
            "chassis %(chassis)s and anchoring internal LRP %(lrp)s",
            {
                "net": network_id,
                "router": router_id,
                "chassis": list(chassis_prio),
                "lrp": lrp_name,
            },
        )

        admin_context = n_context.get_admin_context()
        with nb_idl.transaction(check_error=True) as txn:
            # Populate the per-network unified HCG with the gateway chassis.
            # This is what fixes the external (baremetal) ports, which already
            # reference neutron-<network_id>.
            hcg, _ = ovn_utils.sync_ha_chassis_group_network_unified(
                admin_context,
                nb_idl,
                client._sb_idl,
                network_id,
                router_id,
                chassis_prio,
                txn,
            )

            # Anchor the internal router-interface LRP to the same unified HCG.
            if nb_idl.lookup("Logical_Router_Port", lrp_name, default=None):
                txn.add(
                    nb_idl.db_set(
                        "Logical_Router_Port",
                        lrp_name,
                        ("ha_chassis_group", hcg),
                    )
                )
    except Exception as err:
        LOG.error(
            "Failed linking HA_Chassis_Group for network %(net)s port "
            "%(port)s (router %(router)s): %(error)s",
            {
                "net": network_id,
                "port": port_id,
                "router": router_id,
                "error": err,
            },
        )


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
    LOG.debug(
        "handle_router_interface_removal received %(payload)s", {"payload": payload}
    )
    port = payload.metadata["port_db"]
    network_id = payload.metadata["network"]["id"]

    if port.device_owner not in ROUTER_INTERFACE_AND_GW:
        return

    LOG.info(
        "Router interface removal: port %(port)s router %(router)s network "
        "%(network)s owner %(owner)s",
        {
            "port": port.id,
            "router": port.device_id,
            "network": network_id,
            "owner": port.device_owner,
        },
    )

    if not is_only_router_port_on_network(network_id):
        LOG.info(
            "Router interface removal: port %(port)s router %(router)s on "
            "network %(network)s is not the last router interface, skipping "
            "shared infrastructure cleanup",
            {
                "port": port.id,
                "router": port.device_id,
                "network": network_id,
            },
        )
        return

    segment = fetch_router_network_segment(network_id)
    if not segment:
        return

    LOG.info(
        "Router interface removal: last router interface on network %(network)s "
        "— cleaning shared infrastructure for segment %(segment)s vlan %(vlan)s",
        {
            "network": network_id,
            "segment": segment["id"],
            "vlan": segment.get("segmentation_id"),
        },
    )

    shared_port = fetch_shared_router_port(segment)
    if not shared_port:
        return

    handle_subport_removal(shared_port)
    delete_uplink_port(segment, network_id)
    shared_port.delete()
    LOG.info(
        "Router interface removal complete: network %(network)s segment "
        "%(segment)s shared_port %(port)s cleaned up",
        {
            "network": network_id,
            "segment": segment["id"],
            "port": shared_port["id"],
        },
    )


def handle_subport_removal(port: Port) -> None:
    """Removes router's subport from a network node trunk."""
    trunk_id = utils.fetch_network_node_trunk_id()
    port_id = port["id"]
    LOG.info(
        "Removing router shared subport %(port)s from trunk %(trunk)s",
        {"port": port_id, "trunk": trunk_id},
    )
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
            "No router shared ports found for segment %(segment)s", {"segment": segment}
        )
        return
    LOG.debug("Router shared ports found %(ports)s", {"ports": shared_ports})
    return shared_ports[0]
