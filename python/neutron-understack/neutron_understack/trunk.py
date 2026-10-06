from neutron.objects.network import NetworkSegment
from neutron.objects.ports import Port
from neutron.objects.trunk import SubPort
from neutron.services.trunk.drivers import base as trunk_base
from neutron.services.trunk.models import Trunk
from neutron_lib import constants as p_const
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
        "VLAN %(seg_id)s on physical network %(physical_network)s cannot be "
        "used as both the native VLAN for trunk %(trunk_id)s and the "
        "segmentation ID for subport %(subport_id)s."
    )


class SubportSegmentationIDRangeError(exc.NeutronException):
    message = (
        "VLAN %(seg_id)s for subport %(subport_id)s is outside the configured "
        "tenant trunk VLAN range %(minimum)s-%(maximum)s."
    )


def _missing_physnet_msg(port_id: str) -> str:
    """physical_network names the segment range a subport allocates from."""
    return (
        "physical_network is required in the binding_profile for baremetal port "
        f"trunk configuration, but port {port_id} does not have one."
    )


def subport_vif_type(status: str) -> str:
    """A subport is bound to the switchport, via its parent, while the trunk is up."""
    if status == trunk_consts.TRUNK_ACTIVE_STATUS:
        return portbindings.VIF_TYPE_OTHER
    return portbindings.VIF_TYPE_UNBOUND


def subport_port_status(status: str) -> str:
    """A subport's port status follows its trunk's."""
    if status == trunk_consts.TRUNK_ACTIVE_STATUS:
        return p_const.PORT_STATUS_ACTIVE
    return p_const.PORT_STATUS_DOWN


def claim_subports(
    parent_port_id: str, subports: list[SubPort | dict], status: str
) -> None:
    """Claim the supplied subports and write the binding Nova reads from them."""
    if not subports:
        return
    port_status = subport_port_status(status)
    vif_type = subport_vif_type(status)
    # One transaction for every subport, so a failure leaves none of them
    # half-written.
    with utils.get_admin_session() as session:
        claimed = set(
            utils.update_port_fields_if_owner(
                session,
                [subport["port_id"] for subport in subports],
                {
                    "device_owner": trunk_consts.TRUNK_SUBPORT_OWNER,
                    "status": port_status,
                },
                trunk_consts.TRUNK_SUBPORT_OWNER,
            )
        )
        if claimed:
            utils.set_subports_trunk_binding(
                session,
                parent_port_id,
                {
                    subport["port_id"]: subport["segmentation_id"]
                    for subport in subports
                    if subport["port_id"] in claimed
                },
                vif_type,
            )


def trunk_state_is_current(context, trunk: Trunk, status: str) -> bool:
    """Whether the trunk and all its subports already have the state for status.

    Takes a trunk freshly read, as its status is compared as it stands.
    """
    if trunk.status != status:
        return False
    if not trunk.sub_ports:
        return True
    return utils.subports_in_state(
        context,
        trunk.port_id,
        {sub["port_id"]: sub["segmentation_id"] for sub in trunk.sub_ports},
        trunk_consts.TRUNK_SUBPORT_OWNER,
        subport_port_status(status),
        subport_vif_type(status),
    )


def update_trunk_state(trunk: Trunk, subports: list[SubPort], status: str) -> None:
    """Claim the supplied subports and record their trunk's state."""
    claim_subports(trunk.port_id, subports, status)
    LOG.debug("setting trunk %s status to %s", trunk.id, status)
    trunk.update(status=status)


class UnderstackTrunkDriver(trunk_base.DriverBase):
    @property
    def is_loaded(self):
        try:
            return "understack" in cfg.CONF.ml2.mechanism_drivers
        except cfg.NoSuchOptError:
            return False

    @classmethod
    def create(cls):
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
            self.trunk_created_post,
            resources.TRUNK,
            events.AFTER_CREATE,
            cancellable=True,
        )
        registry.subscribe(
            self.trunk_deleted,
            resources.TRUNK,
            events.AFTER_DELETE,
            cancellable=True,
        )

    @staticmethod
    def _prepare_trunk_state(trunk: Trunk, subports: list[SubPort]) -> None:
        """Claim subports DOWN until fabric reconciliation is requested."""
        parent_port = utils.fetch_port_object(trunk.port_id)
        if not utils.is_port_baremetal(parent_port):
            return
        update_trunk_state(trunk, subports, trunk_consts.TRUNK_DOWN_STATUS)

    @staticmethod
    def _release_subports(subports: list[SubPort]) -> None:
        """Return ports that are leaving the trunk to an unowned DOWN state."""
        # Written straight to the port row, as ml2/ovn did: update_port_status()
        # would re-enter the mechanism drivers, and a revision bump would send
        # ovn's maintenance worker chasing an LSP that has not changed.
        with utils.get_admin_session() as session:
            released = utils.update_port_fields_if_owner(
                session,
                [subport["port_id"] for subport in subports],
                {"device_owner": "", "status": p_const.PORT_STATUS_DOWN},
                trunk_consts.TRUNK_SUBPORT_OWNER,
                include_unowned=False,
            )
            if released:
                utils.clear_subports_trunk_binding(session, released)

    def _handle_tenant_vlan_id_and_switchport_config(
        self, subports: list[SubPort], trunk: Trunk
    ) -> None:
        parent_port_obj = utils.fetch_port_object(trunk.port_id)
        self._check_subports_segmentation_id(subports, trunk.id, parent_port_obj)

        if utils.parent_port_is_bound(parent_port_obj):
            self._add_subports_networks_to_parent_port_switchport(
                parent_port_obj, subports
            )

    def _check_subports_segmentation_id(
        self, subports: list[SubPort], trunk_id: str, parent_port: Port
    ) -> None:
        """Validate tenant tags and reject a parent native VLAN collision.

        A switchport cannot have a mapped VLAN ID equal to the native VLAN ID.
        Resolve the native VLAN from the parent port's network and physical
        network so that multi-segment networks are checked against the segment
        used on this particular switch.

        The network-node trunk is exempt because its segmentation IDs are
        internally allocated fabric VLANs, not tenant-selected mapped VLANs.
        They are the same tags as the subports' network segments, so they also
        cannot conflict with the parent through VLAN mapping.
        """
        if trunk_id == utils.fetch_network_node_trunk_id():
            return

        minimum, maximum = cfg.CONF.ml2_understack.default_tenant_vlan_id_range
        for subport in subports:
            seg_id = int(subport["segmentation_id"])
            if not minimum <= seg_id <= maximum:
                raise SubportSegmentationIDRangeError(
                    seg_id=seg_id,
                    subport_id=subport["port_id"],
                    minimum=minimum,
                    maximum=maximum,
                )

        if not utils.parent_port_is_bound(parent_port):
            return

        physical_network = parent_port.bindings[0].profile.get("physical_network")
        if not physical_network:
            # The create path reports the more specific missing-physnet error
            # when it attempts to configure the parent switchport.
            return

        native_segment = utils.network_segment_by_physnet(
            network_id=parent_port.network_id,
            physnet=physical_network,
        )
        if native_segment is None:
            return

        self._check_native_vlan_conflict(
            subports=subports,
            trunk_id=trunk_id,
            physical_network=physical_network,
            native_vlan_id=native_segment.segmentation_id,
        )

    def _check_native_vlan_conflict(
        self,
        subports: list[SubPort] | list[dict],
        trunk_id: str,
        physical_network: str,
        native_vlan_id: int,
    ) -> None:
        """Enforce the trunk's native/tagged VLAN uniqueness invariant."""
        native_vlan_id = int(native_vlan_id)
        for subport in subports:
            seg_id = int(subport["segmentation_id"])
            if seg_id == native_vlan_id:
                raise SubportSegmentationIDError(
                    seg_id=seg_id,
                    subport_id=subport["port_id"],
                    trunk_id=trunk_id,
                    physical_network=physical_network,
                )

    def check_trunk_native_vlan(
        self,
        trunk_details: dict,
        physical_network: str,
        native_vlan_id: int,
    ) -> None:
        """Check a candidate parent native VLAN against existing subports."""
        if trunk_details["trunk_id"] == utils.fetch_network_node_trunk_id():
            return

        self._check_native_vlan_conflict(
            subports=trunk_details.get("sub_ports", []),
            trunk_id=trunk_details["trunk_id"],
            physical_network=physical_network,
            native_vlan_id=native_vlan_id,
        )

    def configure_trunk(
        self,
        trunk_details: dict,
        port_id: str,
        physical_network: str,
        native_vlan_id: int,
    ) -> None:
        self.check_trunk_native_vlan(
            trunk_details=trunk_details,
            physical_network=physical_network,
            native_vlan_id=native_vlan_id,
        )
        subports = trunk_details.get("sub_ports", [])
        parent_port_obj = utils.fetch_port_object(port_id)
        self._add_subports_networks_to_parent_port_switchport(
            parent_port=parent_port_obj, subports=subports
        )

    def _handle_segment_allocation(
        self, subports: list[SubPort], physnet: str, binding_host: str
    ) -> set:
        allowed_vlan_ids = set()
        for subport in subports:
            subport_network_id = utils.fetch_subport_network_id(
                subport_id=subport["port_id"]
            )
            current_segment = utils.network_segment_by_physnet(
                network_id=subport_network_id,
                physnet=physnet,
            )
            network_segment = current_segment or utils.allocate_dynamic_segment(
                network_id=subport_network_id,
                physnet=physnet,
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
        parent_binding = utils.active_port_binding(parent_port)
        binding_profile = parent_binding.profile
        binding_host = parent_binding.host

        physnet = binding_profile.get("physical_network")
        if not physnet:
            # Reached from the PRECOMMIT_CREATE handlers, so raising here aborts
            # the transaction and surfaces the error to the API caller.
            raise exc.BadRequest(
                resource="port", msg=_missing_physnet_msg(parent_port.id)
            )

        self._handle_segment_allocation(subports, physnet, binding_host)

    def clean_trunk(self, trunk_details: dict, host: str) -> None:
        self._handle_segment_deallocation(trunk_details.get("sub_ports", []), host)

    def _clean_parent_port_switchport_config(
        self, parent_port: Port, subports: list[SubPort]
    ) -> None:
        if not utils.parent_port_is_bound(parent_port):
            return
        parent_binding = utils.active_port_binding(parent_port)
        self._handle_segment_deallocation(subports, parent_binding.host)

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

    def subports_added(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def subports_added_post(self, resource, event, trunk_plugin, payload):
        self._prepare_trunk_state(payload.states[0], payload.metadata["subports"])

    def subports_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        parent_port = utils.fetch_port_object(trunk.port_id)
        self._clean_parent_port_switchport_config(parent_port, subports)
        if not utils.is_port_baremetal(parent_port):
            return
        self._release_subports(subports)

    def trunk_created(self, resource, event, trunk_plugin, payload):
        trunk = payload.latest_state
        subports = trunk.sub_ports
        if subports:
            self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def trunk_created_post(self, resource, event, trunk_plugin, payload):
        """Claim its subports DOWN until fabric reconciliation is requested."""
        trunk = payload.states[0]
        self._prepare_trunk_state(trunk, trunk.sub_ports)

    def trunk_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = trunk.sub_ports
        if subports:
            parent_port = utils.fetch_port_object(trunk.port_id)
            self._clean_parent_port_switchport_config(parent_port, subports)
            if utils.is_port_baremetal(parent_port):
                self._release_subports(subports)
