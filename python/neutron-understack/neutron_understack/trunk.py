from neutron.objects.network import NetworkSegment
from neutron.objects.ports import Port
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
from neutron_understack.network_node_trunk import fetch_network_node_trunk_id

LOG = log.getLogger(__name__)

SUPPORTED_INTERFACES = (portbindings.VIF_TYPE_OTHER,)

SUPPORTED_SEGMENTATION_TYPES = (trunk_consts.SEGMENTATION_TYPE_VLAN,)


class SubportSegmentationIDError(exc.NeutronException):
    message = (
        "Segmentation ID: %(seg_id)s cannot be set to the Subport: "
        "%(subport_id)s as it falls outside of allowed ranges: "
        "%(network_segment_ranges)s. Please use different Segmentation ID."
    )


def _missing_physnet_msg(port_id: str) -> str:
    """Explain that a parent port cannot be configured without a physnet.

    physical_network names the VLAN group that undersync configures, so
    without it there is no switch to push the trunk's subport VLANs to.
    """
    return (
        "physical_network is required in the binding_profile for baremetal port "
        f"trunk configuration, but port {port_id} does not have one."
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
            self.subports_deleted_precommit,
            resources.SUBPORTS,
            events.PRECOMMIT_DELETE,
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
            self.trunk_deleted_precommit,
            resources.TRUNK,
            events.PRECOMMIT_DELETE,
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
        if trunk_id == fetch_network_node_trunk_id():
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

        vlan_group_name = binding_profile.get("physical_network")
        if not vlan_group_name:
            # Reached from the PRECOMMIT_CREATE handlers, so raising here aborts
            # the transaction and surfaces the error to the API caller.
            raise exc.BadRequest(
                resource="port", msg=_missing_physnet_msg(parent_port.id)
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

        vlan_group_name = binding_profile.get("physical_network")
        if not vlan_group_name:
            # This runs postcommit: the subports are already gone from the DB,
            # so raising cannot roll anything back. The PRECOMMIT_DELETE
            # handlers reject this case while it is still abortable; getting
            # here means the binding profile changed underneath us. Log it and
            # still release the segments -- otherwise their VLANs leak -- but
            # skip the undersync call, since there is no vlan group to sync.
            LOG.error(_missing_physnet_msg(parent_port_obj.id))
        self._handle_subports_removal(
            binding_profile=binding_profile,
            binding_host=binding_host,
            subports=subports,
            vlan_group_name=vlan_group_name,
        )

    def _delete_unused_segment(self, segment_id: str) -> NetworkSegment:
        network_segment = utils.network_segment_by_id(segment_id)
        if not utils.ports_bound_to_segment(
            segment_id
        ) and utils.is_dynamic_network_segment(segment_id):
            utils.release_dynamic_segment(segment_id)
        return network_segment

    def _handle_segment_deallocation(self, subports: list[SubPort], host: str):
        for subport in subports:
            binding_level = utils.port_binding_level_by_port_id(
                subport["port_id"], host
            )
            if binding_level:
                binding_level.delete()
                self._delete_unused_segment(binding_level.segment_id)

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
            self.undersync.sync(vlan_group_name)

    def subports_added(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def subports_added_post(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        parent_port = utils.fetch_port_object(trunk.port_id)

        if utils.parent_port_is_bound(parent_port):
            binding_profile = parent_port.bindings[0].profile
            vlan_group_name = binding_profile.get("physical_network")
            if not vlan_group_name:
                # subports_added validates the same parent port on
                # PRECOMMIT_CREATE, so normally we never get here. This runs
                # postcommit, where raising cannot undo the subport creation,
                # and there is no vlan group to sync.
                LOG.error(_missing_physnet_msg(parent_port.id))
                return
            LOG.debug("subports_added_post found vlan_group_name=%s", vlan_group_name)
            self.undersync.sync(vlan_group_name)

    def _validate_parent_port_physnet(self, trunk: Trunk) -> None:
        """Reject a teardown whose parent port has no physical_network.

        The switchport teardown itself runs on AFTER_DELETE, where the rows are
        already committed and an exception cannot roll them back, so the check
        has to happen here while the transaction can still be aborted.
        """
        parent_port_obj = utils.fetch_port_object(trunk.port_id)
        if not utils.parent_port_is_bound(parent_port_obj):
            return
        if not parent_port_obj.bindings[0].profile.get("physical_network"):
            raise exc.BadRequest(
                resource="port", msg=_missing_physnet_msg(parent_port_obj.id)
            )

    def subports_deleted_precommit(self, resource, event, trunk_plugin, payload):
        self._validate_parent_port_physnet(payload.states[0])

    def subports_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        self._clean_parent_port_switchport_config(trunk, subports)

    def trunk_created(self, resource, event, trunk_plugin, payload):
        trunk = payload.latest_state
        subports = trunk.sub_ports
        if subports:
            self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def trunk_deleted_precommit(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        if trunk.sub_ports:
            self._validate_parent_port_physnet(trunk)

    def trunk_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = trunk.sub_ports
        if subports:
            self._clean_parent_port_switchport_config(trunk, subports)
