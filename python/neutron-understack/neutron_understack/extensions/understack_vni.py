from neutron_lib.api import extensions

from neutron_understack.api.definitions import understack_vni as apidef


# This descriptor carries Understack's own ``understack_vni`` alias. It is only
# applied to routers when the UnderstackVniPlugin advertises that alias (see
# vrf._supported_extension_aliases); when core owns EVPN the plugin advertises
# core's ``evpn`` alias instead, so this descriptor is loaded but never applied.
class Understack_vni(extensions.APIExtensionDescriptor):
    api_definition = apidef
