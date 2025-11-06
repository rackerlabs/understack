import logging
import uuid
from contextlib import contextmanager

from neutron.common.ovn import constants as ovn_const
from neutron.db import models_v2
from neutron.objects import ports as port_obj
from neutron.objects import trunk as trunk_obj
from neutron.objects.network import NetworkSegment
from neutron.objects.network_segment_range import NetworkSegmentRange
from neutron.plugins.ml2.driver_context import portbindings
from neutron.services.trunk.plugin import TrunkPlugin
from neutron_lib import constants
from neutron_lib import constants as p_const
from neutron_lib import context as n_context
from neutron_lib.api.definitions import segment as segment_def
from neutron_lib.plugins import directory
from neutron_lib.plugins.ml2 import api
from oslo_config import cfg

from neutron_understack.ironic import IronicClient
from neutron_understack.ml2_type_annotations import NetworkSegmentDict
from neutron_understack.ml2_type_annotations import PortContext
from neutron_understack.ml2_type_annotations import PortDict

LOG = logging.getLogger(__name__)


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


def _is_uuid(value: str) -> bool:
    """Check if a string is a UUID."""
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _get_gateway_agent_host(core_plugin, context):
    """Get the host of an alive OVN Controller Gateway agent.

    Args:
        core_plugin: Neutron core plugin instance
        context: Neutron context

    Returns:
        str: Gateway agent host (may be hostname or UUID)

    Raises:
        Exception: If no alive gateway agents found
    """
    LOG.debug("Looking for OVN Controller Gateway agents")
    gateway_agents = core_plugin.get_agents(
        context,
        filters={"agent_type": [ovn_const.OVN_CONTROLLER_GW_AGENT], "alive": [True]},
    )

    if not gateway_agents:
        raise Exception(
            "No alive OVN Controller Gateway agents found. "
            "Please ensure the network node is running and the "
            "OVN gateway agent is active."
        )

    # Use the first gateway agent's host
    # TODO: In the future, support multiple gateway agents for HA
    gateway_host = gateway_agents[0]["host"]
    LOG.debug(
        "Found OVN Gateway agent on host: %s (agent_id: %s)",
        gateway_host,
        gateway_agents[0]["id"],
    )
    return gateway_host


def _resolve_gateway_host(gateway_host):
    """Resolve gateway host to both hostname and UUID.

    This function ensures we have both the hostname and UUID for the gateway host,
    regardless of which format the OVN agent reports. This is necessary because
    some ports may be bound using hostname while others use UUID.

    Args:
        gateway_host: Gateway host (hostname or UUID)

    Returns:
        tuple: (hostname, uuid) - both values will be populated

    Raises:
        Exception: If resolution via Ironic fails
    """
    ironic_client = IronicClient()

    if _is_uuid(gateway_host):
        # Input is UUID, resolve to hostname
        LOG.debug(
            "Gateway host %s is a baremetal UUID, resolving to hostname via Ironic",
            gateway_host,
        )
        gateway_node_uuid = gateway_host
        resolved_name = ironic_client.baremetal_node_name(gateway_node_uuid)

        if not resolved_name:
            raise Exception(
                f"Failed to resolve baremetal node UUID {gateway_node_uuid} "
                "to hostname via Ironic"
            )

        LOG.debug(
            "Resolved gateway baremetal node %s to hostname %s",
            gateway_node_uuid,
            resolved_name,
        )
        return resolved_name, gateway_node_uuid
    else:
        # Input is hostname, resolve to UUID
        LOG.debug(
            "Gateway host %s is a hostname, resolving to UUID via Ironic",
            gateway_host,
        )
        gateway_hostname = gateway_host
        resolved_uuid = ironic_client.baremetal_node_uuid(gateway_hostname)

        if not resolved_uuid:
            raise Exception(
                f"Failed to resolve hostname {gateway_hostname} "
                "to baremetal node UUID via Ironic"
            )

        LOG.debug(
            "Resolved gateway hostname %s to baremetal node UUID %s",
            gateway_hostname,
            resolved_uuid,
        )
        return gateway_hostname, resolved_uuid


def _find_ports_bound_to_hosts(context, host_filters):
    """Find ports bound to any of the specified hosts.

    Args:
        context: Neutron context
        host_filters: List of hostnames/UUIDs to match

    Returns:
        list: Port objects bound to the specified hosts

    Raises:
        Exception: If no ports found
    """
    LOG.debug("Searching for ports bound to hosts: %s", host_filters)

    # Query PortBinding objects for each host (more efficient than fetching all ports)
    gateway_port_ids = set()
    for host in host_filters:
        bindings = port_obj.PortBinding.get_objects(context, host=host)
        for binding in bindings:
            gateway_port_ids.add(binding.port_id)
            LOG.debug("Found port %s bound to gateway host %s", binding.port_id, host)

    if not gateway_port_ids:
        raise Exception(
            f"No ports found bound to gateway hosts (searched for: {host_filters})"
        )

    # Fetch the actual Port objects for the found port IDs
    gateway_ports = [
        port_obj.Port.get_object(context, id=port_id) for port_id in gateway_port_ids
    ]
    # Filter out any None values (in case a port was deleted between queries)
    gateway_ports = [p for p in gateway_ports if p is not None]

    if not gateway_ports:
        raise Exception(
            f"No ports found bound to gateway hosts (searched for: {host_filters})"
        )

    LOG.debug("Found %d port(s) bound to gateway host", len(gateway_ports))
    return gateway_ports


def _find_trunk_by_port_ids(context, port_ids, gateway_host):
    """Find trunk whose parent port is in the given port IDs.

    Args:
        context: Neutron context
        port_ids: List of port IDs to check
        gateway_host: Gateway hostname for logging

    Returns:
        str: Trunk UUID

    Raises:
        Exception: If no matching trunk found
    """
    trunks = trunk_obj.Trunk.get_objects(context)

    if not trunks:
        raise Exception("No trunks found in the system")

    LOG.debug("Checking %d trunk(s) for parent ports in gateway ports", len(trunks))

    for trunk in trunks:
        if trunk.port_id in port_ids:
            LOG.info(
                "Found network node trunk: %s (parent_port: %s, host: %s)",
                trunk.id,
                trunk.port_id,
                gateway_host,
            )
            return str(trunk.id)

    # No matching trunk found
    raise Exception(
        f"Unable to find network node trunk on gateway host '{gateway_host}'. "
        f"Found {len(port_ids)} port(s) bound to gateway host and "
        f"{len(trunks)} trunk(s) in system, but no trunk uses any of the "
        f"gateway ports as parent port. "
        "Please ensure a trunk exists with a parent port on the network node."
    )


_cached_network_node_trunk_id = None


def fetch_network_node_trunk_id() -> str:
    """Dynamically discover the network node trunk ID via OVN Gateway agent.

    This function discovers the network node trunk by:
    1. Finding alive OVN Controller Gateway agents
    2. Getting the host of the gateway agent
    3. Resolve to both hostname and UUID via Ironic (handles both directions)
    4. Query ports bound to either hostname or UUID
    5. Find trunks that use those ports as parent ports

    The network node trunk is used to connect router networks to the
    network node (OVN gateway) by adding subports for each VLAN.

    Note: We need both hostname and UUID because some ports may be bound
    using hostname while others use UUID in their binding_host_id.

    Returns:
        str: The UUID of the network node trunk

    Raises:
        Exception: If no gateway agent or suitable trunk is found

    Example:
        >>> fetch_network_node_trunk_id()
        '2e558202-0bd0-4971-a9f8-61d1adea0427'
    """
    global _cached_network_node_trunk_id
    if _cached_network_node_trunk_id:
        LOG.info(
            "Returning cached network node trunk ID: %s", _cached_network_node_trunk_id
        )
        return _cached_network_node_trunk_id

    context = n_context.get_admin_context()
    core_plugin = directory.get_plugin()

    if not core_plugin:
        raise Exception("Unable to obtain core plugin")

    # Step 1: Get gateway agent host
    gateway_host = _get_gateway_agent_host(core_plugin, context)

    # Step 2: Resolve gateway host if it's a UUID (single Ironic call)
    gateway_host, gateway_node_uuid = _resolve_gateway_host(gateway_host)

    # Step 3: Build host filters (both hostname and UUID if applicable)
    host_filters = [gateway_host]
    if gateway_node_uuid:
        host_filters.append(gateway_node_uuid)

    # Step 4: Find ports bound to gateway host
    gateway_ports = _find_ports_bound_to_hosts(context, host_filters)

    # Step 5: Find trunk using gateway ports
    gateway_port_ids = [port.id for port in gateway_ports]
    _cached_network_node_trunk_id = _find_trunk_by_port_ids(
        context, gateway_port_ids, gateway_host
    )
    LOG.info(
        "Discovered and cached network node trunk ID: %s "
        "(gateway_host: %s, gateway_uuid: %s)",
        _cached_network_node_trunk_id,
        gateway_host,
        gateway_node_uuid,
    )
    return _cached_network_node_trunk_id


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


def fetch_vlan_network_segment_ranges() -> list[NetworkSegmentRange]:
    context = n_context.get_admin_context()

    return NetworkSegmentRange.get_objects(context, network_type="vlan", shared=True)


def allowed_tenant_vlan_id_ranges() -> list[tuple[int, int]]:
    all_vlan_range_objects = fetch_vlan_network_segment_ranges()
    all_vlan_ranges = [(vr.minimum, vr.maximum) for vr in all_vlan_range_objects]
    merged_ranges = merge_overlapped_ranges(all_vlan_ranges)
    default_range = tuple(cfg.CONF.ml2_understack.default_tenant_vlan_id_range)
    return fetch_gaps_in_ranges(merged_ranges, default_range)


def merge_overlapped_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged = []
    for start, end in sorted(ranges):
        if not merged or start > merged[-1][1] + 1:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [tuple(lst) for lst in merged]


def fetch_gaps_in_ranges(
    ranges: list[tuple[int, int]], default_range: tuple[int, int]
) -> list[tuple[int, int]]:
    free_ranges = []
    prev_end = default_range[0] - 1
    for start, end in ranges:
        if start > prev_end + 1:
            free_ranges.append((prev_end + 1, start - 1))
        prev_end = end
    if prev_end < default_range[1]:
        free_ranges.append((prev_end + 1, default_range[1]))
    return free_ranges


def segmentation_id_in_ranges(
    segmentation_id: int, ranges: list[tuple[int, int]]
) -> bool:
    return any(start <= segmentation_id <= end for start, end in ranges)


def printable_ranges(ranges: list[tuple[int, int]]) -> str:
    return ",".join(
        [
            f"{str(tpl[0])}-{str(tpl[1])}" if tpl[0] != tpl[1] else str(tpl[0])
            for tpl in ranges
        ]
    )
