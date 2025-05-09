from uuid import UUID

from neutron.objects import ports as port_obj
from neutron.objects.network import NetworkSegment
from neutron.plugins.ml2.driver_context import portbindings
from neutron_lib import constants
from neutron_lib import context as n_context
from neutron_lib.api.definitions import segment as segment_def
from neutron_lib.plugins import directory

from neutron_understack.ml2_type_annotations import PortContext
from neutron_understack.nautobot import Nautobot


def fetch_port_object(port_id: str) -> port_obj.Port:
    context = n_context.get_admin_context()
    port = port_obj.Port.get_object(context, id=port_id)
    if port is None:
        raise ValueError(f"Failed to fetch Port with ID {port_id}")
    return port


def allocate_dynamic_segment(
    network_id: str,
    network_type: str = "vlan",
    physnet: str | None = None,
) -> dict:
    context = n_context.get_admin_context()
    core_plugin = directory.get_plugin()

    if hasattr(core_plugin.type_manager, "allocate_dynamic_segment"):
        segment_dict = {
            "physical_network": physnet,
            "network_type": network_type,
        }

        segment = core_plugin.type_manager.allocate_dynamic_segment(
            context, network_id, segment_dict
        )
        return segment
    return {}


def create_binding_profile_level(
    port_id: str, host: str, level: int, segment_id: str
) -> port_obj.PortBindingLevel:
    context = n_context.get_admin_context()
    params = {
        "port_id": port_id,
        "host": host,
        "level": level,
        "driver": "understack",
        "segment_id": segment_id,
    }

    pbl = port_obj.PortBindingLevel.get_object(context, **params)
    if not pbl:
        pbl = port_obj.PortBindingLevel(context, **params)
        pbl.create()
    return pbl


def port_binding_level_by_port_id(port_id: str, host: str) -> port_obj.PortBindingLevel:
    context = n_context.get_admin_context()
    return port_obj.PortBindingLevel.get_object(
        context, host=host, level=0, port_id=port_id
    )


def ports_bound_to_segment(segment_id: str) -> list[port_obj.PortBindingLevel]:
    context = n_context.get_admin_context()
    return port_obj.PortBindingLevel.get_objects(context, segment_id=segment_id)


def network_segment_by_id(id: str) -> NetworkSegment:
    context = n_context.get_admin_context()
    return NetworkSegment.get_object(context, id=id)


def network_segment_by_physnet(network_id: str, physnet: str) -> NetworkSegment | None:
    """Fetches vlan network segments for network in particular physnet.

    We return first segment on purpose, there shouldn't be more, but if
    that is the case, it may be intended for some reason and we don't want
    to halt the code.
    """
    context = n_context.get_admin_context()

    segments = NetworkSegment.get_objects(
        context,
        network_id=network_id,
        physical_network=physnet,
        network_type=constants.TYPE_VLAN,
    )
    if not segments:
        return
    return segments[0]


def release_dynamic_segment(segment_id: str) -> None:
    context = n_context.get_admin_context()
    core_plugin = directory.get_plugin()  # Get the core plugin

    if hasattr(core_plugin.type_manager, "release_dynamic_segment"):
        core_plugin.type_manager.release_dynamic_segment(context, segment_id)


def fetch_connected_interface_uuid(binding_profile: dict, nautobot: Nautobot) -> str:
    """Fetches the connected interface UUID from the port's binding profile.

    If the binding_profile contains a UUID then assume this is a nautotbot
    interface UUID, else look up the interface in Nautobot

    :param binding_profile: The binding profile of the port.
    :return: The connected interface UUID.
    """
    local_link_info = binding_profile.get("local_link_information", [{}])[0]
    port_id = local_link_info["port_id"]
    device_name = local_link_info["switch_info"]

    try:
        UUID(str(port_id))
    except ValueError:
        port_id = nautobot.get_interface_uuid(
            device_name=device_name,
            interface_name=port_id,
        )
    return port_id


def parent_port_is_bound(port: port_obj.Port) -> bool:
    port_binding = port.bindings[0]
    return bool(
        port_binding
        and port_binding.vif_type == portbindings.VIF_TYPE_OTHER
        and port_binding.vnic_type == portbindings.VNIC_BAREMETAL
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


def is_baremetal_port(context: PortContext) -> bool:
    return context.current[portbindings.VNIC_TYPE] == portbindings.VNIC_BAREMETAL
