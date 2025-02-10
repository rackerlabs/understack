from neutron.plugins.ml2.drivers import type_vxlan
from neutron_lib import constants as p_const


class UnderstackVxlanTypeDriver(type_vxlan.VxlanTypeDriver):
    """Manage state for EVPN L2VNI networks with ML2."""

    def get_type(self):
        return p_const.TYPE_VXLAN
