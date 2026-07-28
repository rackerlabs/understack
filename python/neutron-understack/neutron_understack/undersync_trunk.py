from neutron.objects.trunk import Trunk
from neutron.services.trunk.drivers import base as trunk_base
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

# name this driver is registered under in the `neutron.ml2.mechanism_drivers`
# entry point namespace, also recorded as PortBindingLevel.driver for any
# port level bound by this mechanism driver.
MECHANISM_DRIVER_NAME = "undersync"

SUPPORTED_INTERFACES = (portbindings.VIF_TYPE_OTHER,)

SUPPORTED_SEGMENTATION_TYPES = (trunk_consts.SEGMENTATION_TYPE_VLAN,)


class PhysicalNetworkNotFoundError(exc.NeutronException):
    message = (
        "No physical_network found in binding profile for parent port "
        "%(port_id)s of trunk %(trunk_id)s, cannot sync undersync."
    )


class UndersyncTrunkDriver(trunk_base.DriverBase):
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
            return MECHANISM_DRIVER_NAME in cfg.CONF.ml2.mechanism_drivers
        except cfg.NoSuchOptError:
            return False

    @classmethod
    def create(cls, plugin_driver):
        cls.plugin_driver = plugin_driver
        # can_trunk_bound_port means that a trunk can be added to an already
        # bound port, which is possible in baremetal environments so always
        # report this as true
        return cls(
            MECHANISM_DRIVER_NAME,
            SUPPORTED_INTERFACES,
            SUPPORTED_SEGMENTATION_TYPES,
            None,
            can_trunk_bound_port=True,
        )

    @registry.receives(resources.TRUNK_PLUGIN, [events.AFTER_INIT])
    def register(self, resource, event, trigger, payload=None):
        super().register(resource, event, trigger, payload=payload)

        # events that we want to listen to and the functions they should
        # call. cancellable=True means that an Exception raised will
        # interrupt / fail the operation that's happening.
        registry.subscribe(
            self.subports_added,
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

    def _sync_parent_port_physical_network(self, trunk: Trunk) -> None:
        parent_port = utils.fetch_port_object(trunk.port_id)
        if not utils.parent_port_is_bound(parent_port):
            return
        if not self._parent_port_bound_by_undersync(parent_port):
            return

        binding_profile = parent_port.bindings[0].profile
        vlan_group_name = binding_profile.get("physical_network")
        if not vlan_group_name:
            raise PhysicalNetworkNotFoundError(
                port_id=parent_port.id, trunk_id=trunk.id
            )

        self.undersync.sync(vlan_group_name)

    @staticmethod
    def _parent_port_bound_by_undersync(parent_port) -> bool:
        return any(
            level.driver == MECHANISM_DRIVER_NAME
            for level in parent_port.binding_levels
        )

    def subports_added(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        self._sync_parent_port_physical_network(trunk)
        trunk.update(status=trunk_consts.TRUNK_ACTIVE_STATUS)

    def subports_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        self._sync_parent_port_physical_network(trunk)
