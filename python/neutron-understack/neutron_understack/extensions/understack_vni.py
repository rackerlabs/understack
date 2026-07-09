from importlib import util as importlib_util

from neutron_lib.api import extensions

try:
    from neutron_lib.api.definitions import evpn as evpn_apidef
except ImportError:
    evpn_apidef = None

from neutron_understack.api.definitions import understack_vni as apidef


def _api_definition():
    if (
        evpn_apidef is not None
        and importlib_util.find_spec("neutron.extensions.evpn") is None
    ):
        return evpn_apidef
    return apidef


class Understack_vni(extensions.APIExtensionDescriptor):
    api_definition = _api_definition()
