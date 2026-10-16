from neutron.objects import trunk as trunk_objects
from neutron.objects.network import NetworkSegment
from neutron.objects.ports import Port
from neutron.objects.trunk import SubPort
from neutron.services.trunk.drivers import base as trunk_base
from neutron.services.trunk.models import Trunk
from neutron_lib import constants as p_const
from neutron_lib import exceptions as exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import events
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.services.trunk import constants as trunk_consts
from oslo_config import cfg
from oslo_log import log

from neutron_understack import utils

LOG = log.getLogger(__name__)

SUPPORTED_INTERFACES = (portbindings.VIF_TYPE_OTHER,)

SUPPORTED_SEGMENTATION_TYPES = (trunk_consts.SEGMENTATION_TYPE_VLAN,)

# Record status after the handlers that push the trunk's config to the fabric
# (they subscribe at PRIORITY_DEFAULT + 1000), so a trunk is only reported ACTIVE
# once that has been asked for. Its own priority group, since neutron-lib stores
# `cancellable` per group.
STATUS_EVENT_PRIORITY = priority_group.PRIORITY_DEFAULT + 2000


class SubportSegmentationIDError(exc.NeutronException):
    message = (
        "Segmentation ID: %(seg_id)s cannot be set to the Subport: "
        "%(subport_id)s as it falls outside of allowed ranges: "
        "%(network_segment_ranges)s. Please use different Segmentation ID."
    )


def _missing_physnet_msg(port_id: str) -> str:
    """physical_network names the segment range a subport allocates from."""
    return (
        "physical_network is required in the binding_profile for baremetal port "
        f"trunk configuration, but port {port_id} does not have one."
    )


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
            priority=STATUS_EVENT_PRIORITY,
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
            priority=STATUS_EVENT_PRIORITY,
            cancellable=True,
        )
        registry.subscribe(
            self.trunk_deleted,
            resources.TRUNK,
            events.AFTER_DELETE,
            cancellable=True,
        )
        registry.subscribe(
            self.parent_port_updated,
            resources.PORT,
            events.AFTER_UPDATE,
        )

    def _set_trunk_status(self, trunk: Trunk, status: str) -> None:
        """Record a trunk's status. Postcommit only.

        This driver owns the status of the trunks it serves: the trunk plugin
        forces DOWN on every create/add/remove, and ml2/ovn deliberately does
        not manage a trunk whose parent LSP is type=external, which is what a
        baremetal parent gets (LP #2167105).
        """
        LOG.debug("setting trunk %s status to %s", trunk.id, status)
        trunk.update(status=status)

    @staticmethod
    def _trunk_status_for_parent(parent_port: Port) -> str:
        """The status a trunk on this parent port should report."""
        if utils.parent_port_is_bound(parent_port):
            return trunk_consts.TRUNK_ACTIVE_STATUS
        return trunk_consts.TRUNK_DOWN_STATUS

    def _record_trunk_state(self, trunk: Trunk, subports: list[SubPort]) -> None:
        """Postcommit: record the trunk's status and claim its subports.

        The matching precommit hook has already written the subports' binding
        levels; pushing them to the fabric is another driver's job,
        and its handler for the same event runs first (STATUS_EVENT_PRIORITY).
        """
        parent_port = utils.fetch_port_object(trunk.port_id)
        if not utils.is_baremetal_parent_port(parent_port):
            return
        status = self._trunk_status_for_parent(parent_port)
        self._claim_subports(subports, status)
        self._set_trunk_status(trunk, status)

    def _claim_subports(self, subports: list[SubPort], trunk_status: str) -> None:
        """Mark these ports as subports of a trunk we serve.

        ml2/ovn used to do this as a side effect of managing our trunks
        (LP #2167105). device_owner is what stops the rest of Neutron -- ovn's
        own update_lsp_host_info() included -- from treating a subport as a
        free port, and a subport is only up if the fabric carries it, which is
        what the trunk's status says.
        """
        self._update_subports(
            subports,
            device_owner=trunk_consts.TRUNK_SUBPORT_OWNER,
            status=(
                p_const.PORT_STATUS_ACTIVE
                if trunk_status == trunk_consts.TRUNK_ACTIVE_STATUS
                else p_const.PORT_STATUS_DOWN
            ),
        )

    def _release_subports(self, subports: list[SubPort]) -> None:
        """Undo _claim_subports() for ports that are leaving the trunk."""
        self._update_subports(
            subports, device_owner="", status=p_const.PORT_STATUS_DOWN
        )

    @staticmethod
    def _update_subports(
        subports: list[SubPort], device_owner: str, status: str
    ) -> None:
        # Written straight to the port row, as ml2/ovn did: update_port_status()
        # would re-enter the mechanism drivers, and a revision bump would send
        # ovn's maintenance worker chasing an LSP that has not changed.
        for subport in subports:
            utils.update_port_fields(
                subport["port_id"],
                {"device_owner": device_owner, "status": status},
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
        if trunk_id == utils.fetch_network_node_trunk_id():
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
        self, trunk: Trunk, subports: list[SubPort]
    ) -> None:
        parent_port_obj = utils.fetch_port_object(trunk.port_id)
        if not utils.parent_port_is_bound(parent_port_obj):
            return
        parent_binding = utils.active_port_binding(parent_port_obj)
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
        self._record_trunk_state(payload.states[0], payload.metadata["subports"])

    def subports_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        self._clean_parent_port_switchport_config(trunk, subports)

        parent_port = utils.fetch_port_object(trunk.port_id)
        if not utils.is_baremetal_parent_port(parent_port):
            return
        self._release_subports(subports)
        self._set_trunk_status(trunk, self._trunk_status_for_parent(parent_port))

    def trunk_created(self, resource, event, trunk_plugin, payload):
        trunk = payload.latest_state
        subports = trunk.sub_ports
        if subports:
            self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def trunk_created_post(self, resource, event, trunk_plugin, payload):
        """A trunk is born DOWN; record its real state once its rows are committed."""
        trunk = payload.states[0]
        self._record_trunk_state(trunk, trunk.sub_ports)

    def parent_port_updated(self, resource, event, trunk_plugin, payload):
        """Follow a trunked parent port to ACTIVE.

        A trunk is usually created before the node is deployed, so the parent's
        vif-attach is the point where its fabric config first exists. ml2/ovn
        does this for its own trunks; ours are not its to manage.
        """
        updated_port = payload.latest_state
        trunk_details = updated_port.get("trunk_details")
        if not trunk_details:
            return
        if updated_port.get("status") != p_const.PORT_STATUS_ACTIVE:
            return
        if payload.states[0].get("status") == p_const.PORT_STATUS_ACTIVE:
            return
        parent_port = utils.fetch_port_object(updated_port["id"])
        if not utils.is_baremetal_parent_port(parent_port):
            return
        if (
            self._trunk_status_for_parent(parent_port)
            != trunk_consts.TRUNK_ACTIVE_STATUS
        ):
            return

        trunk = trunk_objects.Trunk.get_object(
            payload.context, id=trunk_details["trunk_id"]
        )
        if not trunk:
            return
        self._claim_subports(trunk.sub_ports, trunk_consts.TRUNK_ACTIVE_STATUS)
        self._set_trunk_status(trunk, trunk_consts.TRUNK_ACTIVE_STATUS)

    def trunk_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = trunk.sub_ports
        if subports:
            self._clean_parent_port_switchport_config(trunk, subports)
            if utils.is_baremetal_parent_port(utils.fetch_port_object(trunk.port_id)):
                self._release_subports(subports)
