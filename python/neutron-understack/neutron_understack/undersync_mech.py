import logging

from neutron_lib import constants as p_const
from neutron_lib import exceptions as exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import events
from neutron_lib.callbacks import priority_group
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.plugins.ml2 import api
from neutron_lib.plugins.ml2.api import MechanismDriver
from oslo_config import cfg

from neutron_understack import config
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


def _missing_physnet_msg(port_id: str) -> str:
    """physical_network names the VLAN group Undersync configures."""
    return (
        "physical_network is required in the binding_profile for baremetal port "
        f"trunk configuration, but port {port_id} does not have one."
    )


class UndersyncDriver(MechanismDriver):
    """Tells Undersync which vlan groups need their switch config reconciled.

    Sole owner of the Undersync client. Allocates nothing and mutates no trunk
    state: it observes what the understack driver did and names the affected
    physical_network to Undersync.

    Must be listed *after* ``understack`` in ml2 ``mechanism_drivers``: ML2
    invokes ``*_postcommit`` in that order, so understack has finished releasing
    segments and cleaning trunks before we sync.
    """

    @property
    def connectivity(self):  # type: ignore
        return portbindings.CONNECTIVITY_L2

    def initialize(self):
        config.register_ml2_understack_opts(cfg.CONF)
        self.undersync = Undersync(cfg.CONF.ml2_understack.undersync_url)
        self.subscribe()

    def subscribe(self):
        # Reject a teardown we could not notify Undersync about while the
        # transaction can still be aborted; AFTER_DELETE is too late to raise.
        for resource in (resources.SUBPORTS, resources.TRUNK):
            registry.subscribe(
                self._validate_parent_physnet,
                resource,
                events.PRECOMMIT_DELETE,
                cancellable=True,
            )

        for callback, resource, event in (
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
        if not parent_port.bindings[0].profile.get("physical_network"):
            raise exc.BadRequest(
                resource="port", msg=_missing_physnet_msg(parent_port.id)
            )

    def _subports_after_create(self, resource, event, trunk_plugin, payload):
        self._sync_trunk_parent(payload.states[0])

    def _subports_after_delete(self, resource, event, trunk_plugin, payload):
        self._sync_trunk_parent(payload.states[0])

    def _trunk_after_delete(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        if trunk.sub_ports:
            self._sync_trunk_parent(trunk)

    def _sync_trunk_parent(self, trunk) -> None:
        parent_port = utils.fetch_port_object(trunk.port_id)
        if not utils.parent_port_is_bound(parent_port):
            return

        physnet = parent_port.bindings[0].profile.get("physical_network")
        if not physnet:
            # _validate_parent_physnet rejects this while it is still
            # abortable, so the binding profile changed underneath us. Raising
            # postcommit from a cancellable subscription surfaces as a 500.
            LOG.error(_missing_physnet_msg(parent_port.id))
            return

        LOG.debug("notifying Undersync of vlan group %s", physnet)
        self.undersync.sync(physnet)

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
