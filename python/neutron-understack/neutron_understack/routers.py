import logging
from uuid import UUID

from neutron.objects import base as base_obj
from neutron.objects.network import NetworkSegment
from neutron_lib import constants as p_const
from neutron_lib import context as n_context
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from oslo_config import cfg

from neutron_understack import utils

from .ml2_type_annotations import PortContext

LOG = logging.getLogger(__name__)


def create_port_postcommit(context: PortContext, driver):
    """Handles `create_port_postcommit` event for Router ports."""
    port_id = context.current["id"]
    device_id = context.current["device_id"]
    device_owner = context.current["device_owner"]

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
        existing_segment = matching_segments[0]
    else:
        existing_segment = None

    LOG.debug(
        "existing_segment: %(ex)s",
        {"ex": existing_segment},
    )
    utils.vlan_segment_for_physnet(
        context, cfg.CONF.ml2_understack.network_node_switchport_physnet
    )
    segment = existing_segment or create_router_segment(driver, context)

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

    # We need to publish the event below because allocate_dynamic_segment
    # in the Neutron source code does not handle this. OVN requires the event
    # since it creates logical switch ports based on it.
    registry.publish(
        resources.SEGMENT,
        events.AFTER_CREATE,
        driver.create_port_postcommit,
        payload=events.DBEventPayload(
            context, resource_id=segment_obj.id, states=(segment_obj,)
        ),
    )
    LOG.debug("router dynamic segment: %(segment)s", {"segment": segment})
    return segment


def handle_router_interface_removal(_resource, _event, _trigger, payload) -> None:
    """Handles the removal of a router interface.

    When router interface port is delete , we remove the corresponding subport
    from the trunk.
    """
    # trunk_id will be discovered dynamically at some point
    trunk_id = cfg.CONF.ml2_understack.network_node_trunk_uuid
    port = payload.metadata["port"]
    if port["device_owner"] in [p_const.DEVICE_OWNER_ROUTER_INTF]:
        LOG.debug("Router, Removing subport: %s(port)s", {"port": port})
        port_id = port["id"]
        try:
            utils.remove_subport_from_trunk(trunk_id, port_id)
        except Exception as err:
            LOG.error("failed removing_subport: %(error)s", {"error": err})
