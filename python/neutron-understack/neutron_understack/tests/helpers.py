from neutron.db.external_net_db import External_net_db_mixin
from neutron.db.models_v2 import Port
from neutron.db.models_v2 import Subnet
from neutron.plugins.ml2.plugin import Ml2Plugin
from neutron.services.trunk.plugin import TrunkPlugin


class Ml2PluginNoInit(Ml2Plugin):
    """Ml2Plugin helper class.

    This class is meant to help us use Ml2Plugin methods bypassing original
    __init__ to avoid notifiers and db connections.
    """

    def __init__(self):
        pass

    def construct_port_dict(self, port: Port) -> dict:
        port_dict = self._make_port_dict(port, process_extensions=False)
        self._update_port_dict_binding(port_dict, port.port_bindings[0])
        return port_dict

    def construct_subnet_dict(self, subnet: Subnet) -> dict:
        base_subnet_dict = self._make_subnet_dict(subnet)
        extended_subnet_dict = External_net_db_mixin._extend_subnet_dict_l3(
            base_subnet_dict, subnet
        )
        return extended_subnet_dict


def extend_port_dict_with_trunk(port_dict: dict, port: Port) -> dict:
    port_dict["bulk"] = True
    TrunkPlugin._extend_port_trunk_details(port_dict, port)
    port_dict.pop("bulk")
    return port_dict
