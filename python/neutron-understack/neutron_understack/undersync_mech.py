import logging

from neutron.objects import trunk as trunk_objects
from neutron_lib import constants as p_const
from neutron_lib import exceptions as exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import events
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins.ml2 import api
from neutron_lib.plugins.ml2.api import MechanismDriver
from neutron_lib.services.trunk import constants as trunk_consts
from oslo_config import cfg

from neutron_understack import config
from neutron_understack import trunk as trunk_driver
from neutron_understack import utils
from neutron_understack.undersync_client import Undersync

from .ml2_type_annotations import PortContext

LOG = logging.getLogger(__name__)

SUPPORTED_VNIC_TYPES = [portbindings.VNIC_BAREMETAL]

# Run after the understack trunk driver's handler for the same event, so its
# segment deallocation has finished before we tell Undersync to reconcile.
# neutron-lib sorts subscribers ascending and understack uses PRIORITY_DEFAULT.
# A distinct priority is also required because neutron-lib stores `cancellable`
# per priority *group*: mechanism drivers initialize before the trunk plugin, so
# sharing the default group would let our flag decide the trunk driver's.
TRUNK_EVENT_PRIORITY = priority_group.PRIORITY_DEFAULT + 1000


class MechanismDriverOrderError(exc.NeutronException):
    message = (
        "The undersync mechanism driver must be listed after understack in "
        "[ml2] mechanism_drivers, but the configured order is %(drivers)s."
    )


def _missing_physnet_msg(port_id: str) -> str:
    """physical_network names the VLAN group Undersync configures."""
    return (
        "physical_network is required in the binding_profile for baremetal port "
        f"trunk configuration, but port {port_id} does not have one."
    )


class UndersyncDriver(MechanismDriver):
    """Tells Undersync which vlan groups need their switch config reconciled.

    Sole owner of the Undersync client. It allocates nothing: it observes what
    the understack driver did, names the affected physical_network to
    Undersync, and marks the affected trunk ACTIVE once sync() returns.

    Must be listed *after* ``understack`` in ml2 ``mechanism_drivers``: ML2
    invokes ``*_postcommit`` in that order, so understack has finished releasing
    segments and cleaning trunks before we sync. ``initialize()`` refuses to
    start otherwise.
    """

    @property
    def connectivity(self):  # type: ignore
        return portbindings.CONNECTIVITY_L2

    def initialize(self):
        self._check_driver_order()
        config.register_ml2_understack_opts(cfg.CONF)
        self.undersync = Undersync(cfg.CONF.ml2_understack.undersync_url)
        self.subscribe()

    @staticmethod
    def _check_driver_order() -> None:
        """Fail at startup rather than drift silently at runtime.

        Listed first, this driver would tell Undersync to reconcile before
        understack has released the port's segment, so the old VLAN would stay
        on the switch until the next sync of that vlan group.
        """
        drivers = list(cfg.CONF.ml2.mechanism_drivers)
        if "understack" not in drivers or "undersync" not in drivers:
            return
        if drivers.index("undersync") < drivers.index("understack"):
            raise MechanismDriverOrderError(drivers=",".join(drivers))

    def subscribe(self):
        # Reject a teardown we could not notify Undersync about while the
        # transaction can still be aborted; AFTER_DELETE is too late to raise.
        # PRIORITY_DEFAULT is fine here: a failed precommit callback always
        # raises, whatever the group's cancellable flag says.
        for resource in (resources.SUBPORTS, resources.TRUNK):
            registry.subscribe(
                self._validate_parent_physnet,
                resource,
                events.PRECOMMIT_DELETE,
                cancellable=True,
            )

        for callback, resource, event in (
            (self._trunk_after_create, resources.TRUNK, events.AFTER_CREATE),
            (self._subports_after_create, resources.SUBPORTS, events.AFTER_CREATE),
            (self._subports_after_delete, resources.SUBPORTS, events.AFTER_DELETE),
            (self._trunk_after_delete, resources.TRUNK, events.AFTER_DELETE),
        ):
            registry.subscribe(
                callback,
                resource,
                event,
                priority=TRUNK_EVENT_PRIORITY,
                cancellable=True,
            )

    def update_port_postcommit(self, context: PortContext) -> None:
        if self._restore_trunk_subport_binding(context):
            return

        if not utils.is_baremetal_port(context):
            return

        # Only context.original still carries a binding profile once unbound.
        if utils.is_port_unbinding(context):
            port = context.original
        elif utils.is_port_bound_to_switchport(context):
            port = context.current
        else:
            return

        physnet = port[portbindings.PROFILE].get("physical_network")
        if physnet:
            self.undersync.sync(physnet)
            self._record_parent_trunk_state(context)

    @staticmethod
    def _restore_trunk_subport_binding(context: PortContext) -> bool:
        """Ensure a baremetal trunk subport carries the binding we own.

        That is parent_name and tag in its profile, which Nova reads, and the
        vif_type for its parent's state. ML2 unbinds a port and marks it DOWN
        whenever its host or profile is changed through the API, and anything
        else may have left the profile out, so any update to the port repairs
        it. Returns True for a baremetal trunk subport, which has nothing else
        to do here.
        """
        port = context.current
        if port.get("device_owner") != trunk_consts.TRUNK_SUBPORT_OWNER:
            return False

        subport_trunk = utils.fetch_subport_trunk(context.plugin_context, port["id"])
        if not subport_trunk or not utils.binding_is_baremetal(
            subport_trunk.parent_binding
        ):
            return False
        parent_port_id = subport_trunk.parent_port_id
        segmentation_id = subport_trunk.segmentation_id

        status = (
            trunk_consts.TRUNK_ACTIVE_STATUS
            if utils.binding_is_bound(subport_trunk.parent_binding)
            else trunk_consts.TRUNK_DOWN_STATUS
        )
        profile = port.get(portbindings.PROFILE) or {}
        if (
            port[portbindings.VIF_TYPE] != trunk_driver.subport_vif_type(status)
            or profile.get("parent_name") != parent_port_id
            or profile.get("tag") != segmentation_id
        ):
            trunk_driver.claim_subports(
                parent_port_id,
                [{"port_id": port["id"], "segmentation_id": segmentation_id}],
                status,
            )
        return True

    def delete_port_postcommit(self, context: PortContext) -> None:
        # Releasing the segment stays with the understack driver; we only
        # reconcile the switch for the vlan group the port named.
        if not utils.is_baremetal_port(context):
            return

        physnet = context.current[portbindings.PROFILE].get("physical_network")
        if physnet:
            self.undersync.sync(physnet)

    def _validate_parent_physnet(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        # A trunk with no subports has no switchport config to tear down, so it
        # is allowed through even without a physnet.
        if resource == resources.TRUNK and not trunk.sub_ports:
            return

        parent_port = utils.fetch_port_object(trunk.port_id)
        if not utils.parent_port_is_bound(parent_port):
            return
        if not utils.active_port_binding(parent_port).profile.get(api.PHYSICAL_NETWORK):
            raise exc.BadRequest(
                resource="port", msg=_missing_physnet_msg(parent_port.id)
            )

    def _subports_after_create(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        if self._sync_trunk_parent(trunk):
            trunk_driver.update_trunk_state(
                trunk,
                payload.metadata["subports"],
                trunk_consts.TRUNK_ACTIVE_STATUS,
            )

    def _subports_after_delete(self, resource, event, trunk_plugin, payload):
        if self._sync_trunk_parent(payload.states[0]):
            # The post-delete trunk's sub_ports field is unloaded. The original
            # object still addresses the same trunk row; only its status is
            # updated here, while the trunk driver has already released the
            # removed ports.
            trunk = payload.states[0]
            trunk_driver.update_trunk_state(trunk, [], trunk_consts.TRUNK_ACTIVE_STATUS)

    def _trunk_after_create(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        if self._sync_trunk_parent(trunk):
            trunk_driver.update_trunk_state(
                trunk, trunk.sub_ports, trunk_consts.TRUNK_ACTIVE_STATUS
            )

    def _trunk_after_delete(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        if trunk.sub_ports:
            self._sync_trunk_parent(trunk)

    def _sync_trunk_parent(self, trunk) -> bool:
        parent_port = utils.fetch_port_object(trunk.port_id)
        if not utils.parent_port_is_bound(parent_port):
            return False

        physnet = utils.active_port_binding(parent_port).profile.get(
            api.PHYSICAL_NETWORK
        )
        if not physnet:
            # _validate_parent_physnet rejects this while it is still
            # abortable, so the binding profile changed underneath us. Raising
            # postcommit from a cancellable subscription surfaces as a 500.
            LOG.error(_missing_physnet_msg(parent_port.id))
            return False

        LOG.debug("notifying Undersync of vlan group %s", physnet)
        self.undersync.sync(physnet)
        return True

    @staticmethod
    def _record_parent_trunk_state(context: PortContext) -> None:
        trunk_details = context.current.get("trunk_details")
        if not trunk_details:
            return
        trunk = trunk_objects.Trunk.get_object(
            context.plugin_context, id=trunk_details["trunk_id"]
        )
        if not trunk:
            return
        status = (
            trunk_consts.TRUNK_ACTIVE_STATUS
            if utils.is_port_bound_to_switchport(context)
            else trunk_consts.TRUNK_DOWN_STATUS
        )
        if trunk_driver.trunk_state_is_current(context.plugin_context, trunk, status):
            return
        trunk_driver.update_trunk_state(trunk, trunk.sub_ports, status)

    def bind_port(self, context: PortContext) -> None:
        port = context.current
        vnic_type = port.get(portbindings.VNIC_TYPE, portbindings.VNIC_NORMAL)
        LOG.debug(
            "bind_port called for port %s vnic_type %s segments %s",
            port["id"],
            vnic_type,
            context.segments_to_bind,
        )
        if vnic_type not in SUPPORTED_VNIC_TYPES:
            LOG.debug("Skipping unsupported vnic_type %s", vnic_type)
            return

        binding_profile = port.get(portbindings.PROFILE) or {}
        if not binding_profile.get("physical_network"):
            LOG.debug(
                "Skipping port %s without a physical_network in its binding_profile",
                port["id"],
            )
            return

        for segment in context.segments_to_bind:
            if segment[api.NETWORK_TYPE] == p_const.TYPE_VLAN:
                LOG.debug(
                    "bind_port: setting binding for port %s on VLAN segment %s",
                    port["id"],
                    segment,
                )
                context.set_binding(
                    segment_id=segment[api.ID],
                    vif_type=portbindings.VIF_TYPE_OTHER,
                    vif_details={},
                    status=p_const.PORT_STATUS_ACTIVE,
                )
                return

        LOG.warning(
            "bind_port: no VLAN segment found for port %s in %s",
            port["id"],
            context.segments_to_bind,
        )
