from contextlib import contextmanager

from neutron.db import models_v2
from neutron.objects import ports as port_obj
from neutron.objects.network import NetworkSegment
from neutron.plugins.ml2.driver_context import portbindings
from neutron.services.trunk.plugin import TrunkPlugin
from neutron_lib import constants
from neutron_lib import constants as p_const
from neutron_lib import context as n_context
from neutron_lib.api.definitions import segment as segment_def
from neutron_lib.plugins import directory
from neutron_lib.plugins.ml2 import api

from neutron_understack.ml2_type_annotations import NetworkSegmentDict
from neutron_understack.ml2_type_annotations import PortContext
from neutron_understack.ml2_type_annotations import PortDict


def fetch_port_object(port_id: str) -> port_obj.Port:
    context = n_context.get_admin_context()
    port = port_obj.Port.get_object(context, id=port_id)
    if port is None:
        raise ValueError(f"Failed to fetch Port with ID {port_id}")
    return port


def create_neutron_port_for_segment(
    segment: NetworkSegmentDict, context: PortContext
) -> PortDict:
    core_plugin = directory.get_plugin()
    port = {
        "port": {
            "name": f"uplink-{segment['id']}",
            "network_id": context.current["network_id"],
            "mac_address": "",
            "device_owner": "",
            "device_id": "",
            "fixed_ips": [],
            "admin_state_up": True,
            "tenant_id": "",
        }
    }
    if not core_plugin:
        raise Exception("Unable to retrieve core_plugin.")

    return core_plugin.create_port(context.plugin_context, port)


def remove_subport_from_trunk(trunk_id: str, subport_id: str) -> None:
    context = n_context.get_admin_context()
    plugin = fetch_trunk_plugin()
    subports = {
        "sub_ports": [
            {
                "port_id": subport_id,
            },
        ]
    }
    plugin.remove_subports(
        context=context,
        trunk_id=trunk_id,
        subports=subports,
    )


@contextmanager
def get_admin_session():
    session = n_context.get_admin_context().session
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def update_port_fields(port_id: str, fields: dict) -> None:
    with get_admin_session() as session:
        session.query(models_v2.Port).filter_by(id=port_id).update(fields)


def clear_device_id_for_port(port_id: str) -> None:
    update_port_fields(port_id, {"device_id": ""})


def set_device_id_and_owner_for_port(
    port_id: str, device_id: str, device_owner: str
) -> None:
    update_port_fields(port_id, {"device_id": device_id, "device_owner": device_owner})


def fetch_trunk_plugin() -> TrunkPlugin:
    trunk_plugin = directory.get_plugin("trunk")
    if not trunk_plugin:
        raise Exception("unable to obtain trunk plugin")
    return trunk_plugin


def allocate_dynamic_segment(
    network_id: str,
    network_type: str = "vlan",
    physnet: str | None = None,
) -> NetworkSegmentDict:
    context = n_context.get_admin_context()
    core_plugin = directory.get_plugin()

    if not core_plugin:
        raise Exception("unable to obtain core_plugin")

    if hasattr(core_plugin.type_manager, "allocate_dynamic_segment"):
        segment_dict = {
            "physical_network": physnet,
            "network_type": network_type,
        }

        segment = core_plugin.type_manager.allocate_dynamic_segment(
            context, network_id, segment_dict
        )
        return segment
    # TODO: ask Milan when would this be useful
    raise Exception("core type_manager does not support dynamic segment allocation.")


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


def is_dynamic_network_segment(segment_id: str) -> bool:
    segment = network_segment_by_id(segment_id)
    return segment.is_dynamic


def local_link_from_binding_profile(binding_profile: dict) -> dict | None:
    return binding_profile.get("local_link_information", [None])[0]


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


def is_router_interface(context: PortContext) -> bool:
    """Returns True if this port is the internal side of a router."""
    return context.current["device_owner"] in [
        constants.DEVICE_OWNER_ROUTER_INTF,
        constants.DEVICE_OWNER_ROUTER_GW,
    ]


def vlan_segment_for_physnet(
    context: PortContext, physnet: str
) -> NetworkSegmentDict | None:
    for segment in context.network.network_segments:
        if (
            segment[api.NETWORK_TYPE] == p_const.TYPE_VLAN
            and segment[api.PHYSICAL_NETWORK] == physnet
        ):
            return segment
