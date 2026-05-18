from neutron_lib import constants as p_const
from neutron_lib.api.definitions import portbindings
from neutron_lib.plugins.ml2 import api
from neutron_lib.plugins.ml2.api import MechanismDriver

from .ml2_type_annotations import PortContext

SUPPORTED_VNIC_TYPES = [portbindings.VNIC_BAREMETAL, portbindings.VNIC_NORMAL]


class UnderstackUndersyncDriver(MechanismDriver):
    @property
    def connectivity(self):  # type: ignore
        return portbindings.CONNECTIVITY_L2

    def initialize(self):
        pass

    def bind_port(self, context: PortContext) -> None:
        vnic_type = context.current.get(
            portbindings.VNIC_TYPE, portbindings.VNIC_NORMAL
        )
        if vnic_type not in SUPPORTED_VNIC_TYPES:
            return

        for segment in context.segments_to_bind:
            if segment[api.NETWORK_TYPE] == p_const.TYPE_VLAN:
                context.set_binding(
                    segment_id=segment[api.ID],
                    vif_type=portbindings.VIF_TYPE_OTHER,
                    vif_details={},
                    status=p_const.PORT_STATUS_ACTIVE,
                )
                return
