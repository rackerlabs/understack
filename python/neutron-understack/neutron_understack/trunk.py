from neutron.objects.network import NetworkSegment
from neutron.objects.ports import Port
from neutron.objects.ports import PortBindingLevel
from neutron.objects.trunk import SubPort
from neutron.services.trunk.drivers import base as trunk_base
from neutron.services.trunk.models import Trunk
from neutron_lib import exceptions as exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.services.trunk import constants as trunk_consts
from oslo_config import cfg
from oslo_log import log

from neutron_understack import utils

LOG = log.getLogger(__name__)

SUPPORTED_INTERFACES = (portbindings.VIF_TYPE_OTHER,)

SUPPORTED_SEGMENTATION_TYPES = (trunk_consts.SEGMENTATION_TYPE_VLAN,)


class SubportSegmentationIDError(exc.NeutronException):
    message = (
        "Segmentation ID: %(seg_id)s cannot be set to the Subport: "
        "%(subport_id)s as it falls outside of allowed ranges: "
        "%(network_segment_ranges)s. Please use different Segmentation ID."
    )


class UnderStackTrunkDriver(trunk_base.DriverBase):
    def __init__(
        self,
        name,
        interfaces,
        segmentation_types,
        agent_type=None,
        can_trunk_bound_port=False,
    ):
        super().__init__(
            name,
            interfaces,
            segmentation_types,
            agent_type=agent_type,
            can_trunk_bound_port=can_trunk_bound_port,
        )
        self.undersync = self.plugin_driver.undersync
        self.ironic_client = self.plugin_driver.ironic_client

    @property
    def is_loaded(self):
        try:
            return "understack" in cfg.CONF.ml2.mechanism_drivers
        except cfg.NoSuchOptError:
            return False

    @classmethod
    def create(cls, plugin_driver):
        cls.plugin_driver = plugin_driver
        return cls(
            "understack",
            SUPPORTED_INTERFACES,
            SUPPORTED_SEGMENTATION_TYPES,
            None,
            can_trunk_bound_port=True,
        )

    @registry.receives(resources.TRUNK_PLUGIN, [events.AFTER_INIT])
    def register(self, resource, event, trigger, payload=None):
        super().register(resource, event, trigger, payload=payload)

        registry.subscribe(
            self.subports_added,
            resources.SUBPORTS,
            events.PRECOMMIT_CREATE,
            cancellable=True,
        )
        registry.subscribe(
            self.subports_added_post,
            resources.SUBPORTS,
            events.AFTER_CREATE,
            cancellable=True,
        )
        registry.subscribe(
            self.subports_deleted,
            resources.SUBPORTS,
            events.AFTER_DELETE,
            cancellable=True,
        )
        registry.subscribe(
            self.trunk_created,
            resources.TRUNK,
            events.PRECOMMIT_CREATE,
            cancellable=True,
        )
        registry.subscribe(
            self.trunk_deleted,
            resources.TRUNK,
            events.AFTER_DELETE,
            cancellable=True,
        )

    def _handle_tenant_vlan_id_and_switchport_config(
        self, subports: list[SubPort], trunk: Trunk
    ) -> None:
        self._check_subports_segmentation_id(subports, trunk.id)
        parent_port_obj = utils.fetch_port_object(trunk.port_id)

        if utils.parent_port_is_bound(parent_port_obj):
            self._add_subports_networks_to_parent_port_switchport(
                parent_port_obj, subports
            )

    def _check_subports_segmentation_id(
        self, subports: list[SubPort], trunk_id: str
    ) -> None:
        """Checks if a subport's segmentation_id is within the allowed range.

        A switchport cannot have a mapped VLAN ID equal to the native VLAN ID.
        Since the user specifies the VLAN ID (segmentation_id) when adding a
        subport, an error is raised if it falls within any VLAN network segment
        range, as these ranges are used to allocate VLAN tags for all VLAN
        segments, including native VLANs.

        The only case where this check is not required is for a network node
        trunk, since its subport segmentation_ids are the same as the network
        segment VLAN tags allocated to the subports. Therefore, there is no
        possibility of conflict with the native VLAN.
        """
        if trunk_id == cfg.CONF.ml2_understack.network_node_trunk_uuid:
            return

        ns_ranges = utils.allowed_tenant_vlan_id_ranges()
        for subport in subports:
            seg_id = subport.segmentation_id
            if not utils.segmentation_id_in_ranges(seg_id, ns_ranges):
                raise SubportSegmentationIDError(
                    seg_id=seg_id,
                    subport_id=subport.port_id,
                    network_segment_ranges=utils.printable_ranges(ns_ranges),
                )

    def configure_trunk(self, trunk_details: dict, port_id: str) -> None:
        parent_port_obj = utils.fetch_port_object(port_id)
        subports = trunk_details.get("sub_ports", [])
        self._add_subports_networks_to_parent_port_switchport(
            parent_port=parent_port_obj, subports=subports
        )

    def _handle_segment_allocation(
        self, subports: list[SubPort], vlan_group_name: str, binding_host: str
    ) -> set:
        allowed_vlan_ids = set()
        for subport in subports:
            subport_network_id = utils.fetch_subport_network_id(
                subport_id=subport["port_id"]
            )
            current_segment = utils.network_segment_by_physnet(
                network_id=subport_network_id,
                physnet=vlan_group_name,
            )
            network_segment = current_segment or utils.allocate_dynamic_segment(
                network_id=subport_network_id,
                physnet=vlan_group_name,
            )
            allowed_vlan_ids.add(int(network_segment["segmentation_id"]))

            utils.create_binding_profile_level(
                port_id=subport["port_id"],
                host=binding_host,
                level=0,
                segment_id=network_segment["id"],
            )
        return allowed_vlan_ids

    def _add_subports_networks_to_parent_port_switchport(
        self, parent_port: Port, subports: list[SubPort]
    ) -> None:
        binding_profile = parent_port.bindings[0].profile
        binding_host = parent_port.bindings[0].host

        local_link_info = utils.local_link_from_binding_profile(binding_profile)
        vlan_group_name = self.ironic_client.baremetal_port_physical_network(
            local_link_info
        )

        self._handle_segment_allocation(subports, vlan_group_name, binding_host)

    def clean_trunk(
        self, trunk_details: dict, binding_profile: dict, host: str
    ) -> None:
        subports = trunk_details.get("sub_ports", [])
        self._handle_subports_removal(
            binding_profile=binding_profile,
            binding_host=host,
            subports=subports,
            invoke_undersync=False,
        )

    def _clean_parent_port_switchport_config(
        self, trunk: Trunk, subports: list[SubPort]
    ) -> None:
        parent_port_obj = utils.fetch_port_object(trunk.port_id)
        if not utils.parent_port_is_bound(parent_port_obj):
            return
        binding_profile = parent_port_obj.bindings[0].profile
        binding_host = parent_port_obj.bindings[0].host
        local_link_info = utils.local_link_from_binding_profile(binding_profile)
        vlan_group_name = self.ironic_client.baremetal_port_physical_network(
            local_link_info
        )
        self._handle_subports_removal(
            binding_profile=binding_profile,
            binding_host=binding_host,
            subports=subports,
            vlan_group_name=vlan_group_name,
        )

    def _delete_binding_level(self, port_id: str, host: str) -> PortBindingLevel:
        binding_level = utils.port_binding_level_by_port_id(port_id, host)
        binding_level.delete()
        return binding_level

    def _delete_unused_segment(self, segment_id: str) -> NetworkSegment:
        network_segment = utils.network_segment_by_id(segment_id)
        if not utils.ports_bound_to_segment(
            segment_id
        ) and utils.is_dynamic_network_segment(segment_id):
            utils.release_dynamic_segment(segment_id)
        return network_segment

    def _handle_segment_deallocation(self, subports: list[SubPort], host: str):
        for subport in subports:
            subport_binding_level = self._delete_binding_level(subport["port_id"], host)
            self._delete_unused_segment(subport_binding_level.segment_id)

    def _trigger_undersync(self, vlan_group_name: str) -> None:
        self.undersync.sync_devices(
            vlan_group=vlan_group_name,
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def _handle_subports_removal(
        self,
        binding_profile: dict,
        binding_host: str,
        subports: list[SubPort],
        invoke_undersync: bool = True,
        vlan_group_name: str | None = None,
    ) -> None:
        self._handle_segment_deallocation(subports, binding_host)
        if invoke_undersync and vlan_group_name:
            self._trigger_undersync(vlan_group_name)

    def subports_added(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def subports_added_post(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        parent_port = utils.fetch_port_object(trunk.port_id)

        if utils.parent_port_is_bound(parent_port):
            binding_profile = parent_port.bindings[0].profile
            local_link_info = utils.local_link_from_binding_profile(binding_profile)
            vlan_group_name = self.ironic_client.baremetal_port_physical_network(
                local_link_info
            )
            LOG.debug("subports_added_post found vlan_group_name=%s", vlan_group_name)
            self._trigger_undersync(vlan_group_name)

    def subports_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        self._clean_parent_port_switchport_config(trunk, subports)

    def trunk_created(self, resource, event, trunk_plugin, payload):
        trunk = payload.latest_state
        subports = trunk.sub_ports
        if subports:
            self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def trunk_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = trunk.sub_ports
        if subports:
            self._clean_parent_port_switchport_config(trunk, subports)
