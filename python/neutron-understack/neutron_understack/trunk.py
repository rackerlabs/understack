from neutron.db.models_v2 import Port
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
            events.AFTER_CREATE,
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

    def _handle_parent_port_switchport_config(
        self, parent_port_id: str, subport_network_id: str
    ) -> None:
        parent_port_obj = utils.fetch_port_object(parent_port_id)

        if utils.parent_port_is_bound(parent_port_obj):
            self._add_subport_network_to_parent_port_switchport(
                parent_port_obj, subport_network_id
            )

    def _handle_tenant_vlan_id_and_switchport_config(
        self, subports: list[SubPort], trunk: Trunk
    ) -> None:
        for subport in subports:
            subport_network_id = utils.fetch_subport_network_id(
                subport_id=subport.port_id
            )
            self._handle_tenant_vlan_id_config(subport_network_id, subport)

            self._handle_parent_port_switchport_config(
                trunk.port_id, subport_network_id
            )

    def _add_subport_network_to_parent_port_switchport(
        self, parent_port: Port, subport_network_id: str
    ) -> None:
        connected_interface_id = utils.fetch_connected_interface_uuid(
            parent_port.bindings[0].profile, LOG
        )

        vlan_group_id = self.nb.prep_switch_interface(
            connected_interface_id=connected_interface_id,
            ucvni_uuid=subport_network_id,
            vlan_tag=None,
            modify_native_vlan=False,
        )["vlan_group_id"]

        self.undersync.sync_devices(
            vlan_group_uuids=str(vlan_group_id),
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def _remove_subport_network_from_parent_port_switchport(
        self, parent_port: Port, subport_network_id: str
    ) -> None:
        connected_interface_id = utils.fetch_connected_interface_uuid(
            parent_port.bindings[0].profile, LOG
        )

        vlan_group_id = self.nb.detach_port(
            connected_interface_id=connected_interface_id,
            ucvni_uuid=subport_network_id,
        )

        self.undersync.sync_devices(
            vlan_group_uuids=str(vlan_group_id),
            dry_run=cfg.CONF.ml2_understack.undersync_dry_run,
        )

    def _clean_parent_port_switchport_config(
        self, trunk: Trunk, subports: [SubPort]
    ) -> None:
        parent_port_obj = utils.fetch_port_object(trunk.port_id)

        if not utils.parent_port_is_bound(parent_port_obj):
            return

        for subport in subports:
            subport_network_id = utils.fetch_subport_network_id(
                subport_id=subport.port_id
            )
            self._remove_subport_network_from_parent_port_switchport(
                parent_port_obj, subport_network_id
            )

    def subports_added(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def subports_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = payload.metadata["subports"]
        self._clean_parent_port_switchport_config(trunk, subports)

    def trunk_created(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = trunk.sub_ports
        if subports:
            self._handle_tenant_vlan_id_and_switchport_config(subports, trunk)

    def trunk_deleted(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = trunk.sub_ports
        if subports:
            self._clean_parent_port_switchport_config(trunk, subports)
