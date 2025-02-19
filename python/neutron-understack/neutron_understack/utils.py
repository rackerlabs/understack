from neutron.objects import ports as port_obj
from neutron_lib import context as n_context


def fetch_subport_network_id(subport_id):
    context = n_context.get_admin_context()
    neutron_port = port_obj.Port.get_object(context, id=subport_id)
    return neutron_port.network_id
