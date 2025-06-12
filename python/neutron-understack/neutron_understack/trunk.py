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
        "%(subport_id)s as there is already another Segmentation ID: "
        "%(nb_seg_id)s in use by the Network: %(net_id)s that is "
        "attached to the Subport. Please use %(nb_seg_id)s as "
        "segmentation_id for this subport."
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
        self.nb = self.plugin_driver.nb
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

    def _handle_segmentation_id_mismatch(
        self, subport: SubPort, ucvni_uuid: str, tenant_vlan_id: int
    ) -> None:
        subport.delete()
        raise SubportSegmentationIDError(
            seg_id=subport.segmentation_id,
            net_id=ucvni_uuid,
            nb_seg_id=tenant_vlan_id,
            subport_id=subport.port_id,
        )

    def _configure_tenant_vlan_id(self, ucvni_uuid: str, subport: SubPort) -> None:
        subport_seg_id = subport.segmentation_id
        self.nb.add_tenant_vlan_tag_to_ucvni(
            network_uuid=ucvni_uuid, vlan_tag=subport_seg_id
        )
        LOG.info(
            "Segmentation ID: %(seg_id)s is now set on Nautobot's UCVNI "
            "UUID: %(ucvni_uuid)s in the tenant_vlan_id custom field",
            {"seg_id": subport_seg_id, "ucvni_uuid": ucvni_uuid},
        )

    def _handle_tenant_vlan_id_config(
        self, subport_network_id: str, subport: SubPort
    ) -> None:
        ucvni_tenant_vlan_id = self.nb.fetch_ucvni_tenant_vlan_id(
            network_id=subport_network_id
        )
        if not ucvni_tenant_vlan_id:
            self._configure_tenant_vlan_id(
                ucvni_uuid=subport_network_id, subport=subport
            )
        elif ucvni_tenant_vlan_id != subport.segmentation_id:
            self._handle_segmentation_id_mismatch(
                subport=subport,
                ucvni_uuid=subport_network_id,
                tenant_vlan_id=ucvni_tenant_vlan_id,
            )

    def _handle_tenant_vlan_id_and_switchport_config(
        self, subports: list[SubPort], trunk: Trunk
    ) -> None:
        for subport in subports:
            subport_network_id = utils.fetch_subport_network_id(
                subport_id=subport.port_id
            )
            # we don't want to check mappings on network nodes
            if trunk.id == cfg.CONF.ml2_understack.network_node_trunk_uuid:
                continue
            self._handle_tenant_vlan_id_config(subport_network_id, subport)

        parent_port_obj = utils.fetch_port_object(trunk.port_id)

        if utils.parent_port_is_bound(parent_port_obj):
            self._add_subports_networks_to_parent_port_switchport(
                parent_port_obj, subports
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
        connected_interface_id = utils.fetch_connected_interface_uuid(
            binding_profile, self.nb
        )

        local_link_info = utils.local_link_from_binding_profile(binding_profile)
        vlan_group_name = self.ironic_client.baremetal_port_physical_network(
            local_link_info
        )
        allowed_vlan_ids = self._handle_segment_allocation(
            subports, vlan_group_name, binding_host
        )

        self.nb.add_port_vlan_associations(
            interface_uuid=connected_interface_id,
            vlan_group_name=vlan_group_name,
            allowed_vlans_ids=allowed_vlan_ids,
        )

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
            self.nb.delete_vlan(vlan_id=segment_id)
        return network_segment

    def _handle_segment_deallocation(self, subports: list[SubPort], host: str) -> set:
        vlan_ids_to_remove = set()
        for subport in subports:
            subport_binding_level = self._delete_binding_level(subport["port_id"], host)
            network_segment = self._delete_unused_segment(
                subport_binding_level.segment_id
            )
            vlan_ids_to_remove.add(network_segment.id)
        return vlan_ids_to_remove

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
        connected_interface_id = utils.fetch_connected_interface_uuid(
            binding_profile, self.nb
        )

        vlan_ids_to_remove = self._handle_segment_deallocation(subports, binding_host)
        self.nb.remove_port_network_associations(
            interface_uuid=connected_interface_id,
            vlan_ids_to_remove=vlan_ids_to_remove,
        )

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
