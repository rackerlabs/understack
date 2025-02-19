from neutron.objects.trunk import SubPort
from neutron.services.trunk.drivers import base as trunk_base
from neutron_lib import exceptions as exc
from neutron_lib.api.definitions import portbindings
from neutron_lib.callbacks import events
from neutron_lib.callbacks import registry
from neutron_lib.callbacks import resources
from neutron_lib.services.trunk import constants as trunk_consts
from oslo_config import cfg
from oslo_log import log

from neutron_understack import config
from neutron_understack import utils
from neutron_understack.nautobot import Nautobot

config.register_ml2_understack_opts(cfg.CONF)

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
        conf = cfg.CONF.ml2_understack
        self.nb = Nautobot(conf.nb_url, conf.nb_token)

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
            self.trunk_created, resources.TRUNK, events.AFTER_CREATE, cancellable=True
        )

    def _configure_tenant_vlan_id(
        self, tenant_vlan_id: int | None, ucvni_uuid: str, subport: SubPort
    ) -> None:
        subport_seg_id = subport.segmentation_id
        if not tenant_vlan_id:
            self.nb.add_tenant_vlan_tag_to_ucvni(
                network_uuid=ucvni_uuid, vlan_tag=subport_seg_id
            )
            LOG.info(
                "Segmentation ID: %(seg_id)s is now set on Nautobot's UCVNI "
                "UUID: %(ucvni_uuid)s in the tenant_vlan_id custom field",
                {"seg_id": subport_seg_id, "ucvni_uuid": ucvni_uuid},
            )
        elif tenant_vlan_id != subport_seg_id:
            subport.delete()
            raise SubportSegmentationIDError(
                seg_id=subport_seg_id,
                net_id=ucvni_uuid,
                nb_seg_id=tenant_vlan_id,
                subport_id=subport.port_id,
            )

    def _subports_added(self, subports: list[SubPort]) -> None:
        for subport in subports:
            subport_id = subport.port_id
            subport_network_id = utils.fetch_subport_network_id(subport_id=subport_id)
            ucvni_tenant_vlan_id = self.nb.fetch_ucvni_tenant_vlan_id(
                network_id=subport_network_id
            )

            self._configure_tenant_vlan_id(
                tenant_vlan_id=ucvni_tenant_vlan_id,
                ucvni_uuid=subport_network_id,
                subport=subport,
            )

    def subports_added(self, resource, event, trunk_plugin, payload):
        subports = payload.metadata["subports"]
        self._subports_added(subports)

    def trunk_created(self, resource, event, trunk_plugin, payload):
        trunk = payload.states[0]
        subports = trunk.sub_ports
        if subports:
            self._subports_added(subports)
