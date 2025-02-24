import logging

from neutron.db.models.plugins.ml2.vlanallocation import VlanAllocation
from neutron.db.models.segment import NetworkSegment
from neutron_lib import constants as p_const
from neutron_lib import context as neutron_context
from neutron_lib.plugins.ml2.api import NetworkContext
from sqlalchemy import update

LOG = logging.getLogger(__name__)
MAX_VLAN_ATTEMPTS = 4096


class VlanManager:
    def __init__(self, nb, conf):
        self.nb = nb
        self.conf = conf

    def create_vlan_for_network(self, context: NetworkContext):
        """Ensures that Vlan ID for a newly created network is available.

        This method checks if the VLAN is available across the whole fabric,
        and in case where it isn't, it will attempt to allocate new one
        and repeat the checks until successful or we run out of vlans..
        """
        if not context.current:
            raise RuntimeError("no current context provided.")

        vlan_tag = int(context.current["provider:segmentation_id"])
        allocated = self._allocate_vlan(context, vlan_tag)

        if allocated:
            self._update_segmentation_id(context, vlan_tag)
            self._new_vlan_mark_allocated(context, allocated)

    def _allocate_vlan(
        self, context: NetworkContext, vlan_tag: int
    ) -> VlanAllocation | None:
        """Attempts to allocate a VLAN ID, trying multiple times if necessary.

        Returns:
            allocation when new segment was assigned
            None when the original segment was free
        """
        alloc = None
        attempts = 0
        while attempts < MAX_VLAN_ATTEMPTS:
            if self._is_vlan_available(
                self.conf.network_node_switchport_uuid,
                vlan_tag,
            ):
                LOG.debug("Vlan %s is available for all VLANGroups.", vlan_tag)
                return alloc

            LOG.info(
                "Vlan %s is reported to be used in fabric associated with "
                "this VlanGroup. Trying next one...",
                vlan_tag,
            )
            alloc = self._find_next_available_vlan(context)
            vlan_tag = alloc.vlan_id
            attempts += 1
        raise RuntimeError("No available VLANs found after multiple attempts.")

    def _is_vlan_available(self, interface_id: str, vlan_tag: int) -> bool:
        """Checks if VLAN ID is available in Nautobot."""
        return self.nb.check_vlan_availability(
            interface_id=interface_id, vlan_tag=vlan_tag
        )

    def _find_next_available_vlan(self, context):
        """Figures out what the next available VLAN ID for a given network is."""
        if len(context.network_segments) != 1:
            raise ValueError("Multi-segment networks are not supported.")

        vlan_type_driver = context._plugin.type_manager.drivers.get("vlan", {}).obj
        if vlan_type_driver is None:
            raise RuntimeError("no VlanTypeDriver available.")

        admin_context = neutron_context.get_admin_context()
        physical_network = context.current["provider:physical_network"]
        segment_record = vlan_type_driver.allocate_partially_specified_segment(
            context=admin_context, physical_network=physical_network
        )
        return segment_record

    def _update_segmentation_id(self, context, vlan_tag):
        """Updates segmentation ID for the provider and all network segments."""
        context.current["provider:segmentation_id"] = vlan_tag

        # Update all segments' segmentation_id
        session = context.plugin_context.session
        results = []
        for segment in context.network_segments:
            if segment["network_type"] == p_const.TYPE_VLAN:
                results.append(self._update_id_on_segment(session, segment, vlan_tag))
        return results

    def _update_id_on_segment(self, session, segment, vlan_tag):
        """Updates segmentation_id on a single network segment."""
        update_segment_statement = (
            update(NetworkSegment)
            .where(NetworkSegment.id == segment["id"])
            .values(segmentation_id=vlan_tag)
        )

        return session.execute(update_segment_statement)

    def _new_vlan_mark_allocated(self, context, alloc):
        session = context.plugin_context.session
        alloc.allocated = True
        return alloc.save(session)
