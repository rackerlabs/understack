import logging

from neutron_lib import constants as p_const
from neutron_lib.api.definitions import portbindings
from neutron_lib.plugins.ml2 import api
from neutron_lib.plugins.ml2.api import MechanismDriver

from .ml2_type_annotations import PortContext

LOG = logging.getLogger(__name__)

SUPPORTED_VNIC_TYPES = [portbindings.VNIC_BAREMETAL]


class UndersyncDriver(MechanismDriver):
    @property
    def connectivity(self):  # type: ignore
        return portbindings.CONNECTIVITY_L2

    def initialize(self):
        pass

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
