from logging import Logger
from uuid import UUID

from neutron.objects import ports as port_obj
from neutron.plugins.ml2.driver_context import portbindings
from neutron_lib import constants
from neutron_lib import context as n_context
from neutron_lib.api.definitions import segment as segment_def


def fetch_port_object(port_id: str) -> port_obj.Port:
    context = n_context.get_admin_context()
    return port_obj.Port.get_object(context, id=port_id)


def fetch_connected_interface_uuid(
    binding_profile: dict, logger: Logger | None = None
) -> str:
    """Fetches the connected interface UUID from the port's binding profile.

    :param binding_profile: The bindng profile of the port.
    :return: The connected interface UUID.
    """
    connected_interface_uuid = binding_profile.get("local_link_information")[0].get(
        "port_id"
    )
    try:
        UUID(str(connected_interface_uuid))
    except ValueError:
        if logger:
            logger.debug(
                "Local link information port_id is not a valid UUID type"
                " port_id: %(connected_interface_uuid)s",
                {"connected_interface_uuid": connected_interface_uuid},
            )
        raise
    return connected_interface_uuid


def parent_port_is_bound(port: port_obj.Port) -> bool:
    port_binding = port.bindings[0]
    return bool(
        port_binding
        and port_binding.vif_type == portbindings.VIF_TYPE_OTHER
        and port_binding.vnic_type == "baremetal"
        and port_binding.profile
    )


def fetch_subport_network_id(subport_id: str) -> str:
    neutron_port = fetch_port_object(subport_id)
    return neutron_port.network_id


def is_valid_vlan_network_segment(network_segment: dict):
    return (
        network_segment.get(segment_def.NETWORK_TYPE) == constants.TYPE_VLAN
        and network_segment.get(segment_def.PHYSICAL_NETWORK) is not None
    )
