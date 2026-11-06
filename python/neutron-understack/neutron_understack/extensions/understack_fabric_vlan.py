from neutron_lib.api import extensions

from neutron_understack.api.definitions import understack_fabric_vlan as apidef


# Active only when the understack_fabric_vlan ML2 extension driver is enabled.
class Understack_fabric_vlan(extensions.APIExtensionDescriptor):
    api_definition = apidef
