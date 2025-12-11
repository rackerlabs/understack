"""Network node trunk discovery and management.

This module provides functionality to dynamically discover and manage
the network node trunk used for connecting router networks to the
OVN gateway node via VLAN subports.
"""

import logging
import uuid

from neutron.common.ovn import constants as ovn_const
from neutron.objects import ports as port_obj
from neutron.objects import trunk as trunk_obj
from neutron_lib import context as n_context
from neutron_lib.plugins import directory

from neutron_understack.ironic import IronicClient

LOG = logging.getLogger(__name__)

# Global cache for the discovered network node trunk ID
_cached_network_node_trunk_id: str | None = None


def _is_uuid(value: str) -> bool:
    """Check if a string is a valid UUID.

    Args:
        value: String to validate

    Returns:
        True if the string is a valid UUID, False otherwise

    Example:
        >>> _is_uuid("550e8400-e29b-41d4-a716-446655440000")
        True
        >>> _is_uuid("not-a-uuid")
        False
    """
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def _get_gateway_agent_host(core_plugin, context) -> str:
    """Get the host of an alive OVN Controller Gateway agent.

    Args:
        core_plugin: Neutron core plugin instance
        context: Neutron context

    Returns:
        Gateway agent host (may be hostname or UUID)

    Raises:
        Exception: If no alive gateway agents found

    Example:
        >>> _get_gateway_agent_host(plugin, ctx)
        'network-node-01'
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
    gateway_host: str = gateway_agents[0]["host"]
    LOG.debug(
        "Found OVN Gateway agent on host: %s (agent_id: %s)",
        gateway_host,
        gateway_agents[0]["id"],
    )
    return gateway_host


def _resolve_gateway_host(gateway_host: str) -> tuple[str, str]:
    """Resolve gateway host to both hostname and UUID.

    This function ensures we have both the hostname and UUID for the gateway host,
    regardless of which format the OVN agent reports. This is necessary because
    some ports may be bound using hostname while others use UUID.

    Args:
        gateway_host: Gateway host (hostname or UUID)

    Returns:
        Tuple of (hostname, uuid) - both values will be populated

    Raises:
        Exception: If resolution via Ironic fails

    Example:
        >>> _resolve_gateway_host("550e8400-e29b-41d4-a716-446655440000")
        ('network-node-01', '550e8400-e29b-41d4-a716-446655440000')
        >>> _resolve_gateway_host("network-node-01")
        ('network-node-01', '550e8400-e29b-41d4-a716-446655440000')
    """
    ironic_client = IronicClient()

    if _is_uuid(gateway_host):
        # Input is UUID, resolve to hostname
        LOG.debug(
            "Gateway host %s is a baremetal UUID, resolving to hostname via Ironic",
            gateway_host,
        )
        gateway_node_uuid: str = gateway_host
        resolved_name: str | None = ironic_client.baremetal_node_name(gateway_node_uuid)

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
        gateway_hostname: str = gateway_host
        resolved_uuid: str | None = ironic_client.baremetal_node_uuid(gateway_hostname)

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


def _find_ports_bound_to_hosts(context, host_filters: list[str]) -> list[port_obj.Port]:
    """Find ports bound to any of the specified hosts.

    Args:
        context: Neutron context
        host_filters: List of hostnames/UUIDs to match

    Returns:
        List of Port objects bound to the specified hosts

    Raises:
        Exception: If no ports found

    Example:
        >>> _find_ports_bound_to_hosts(ctx, ['network-node-01', 'uuid-123'])
        [<Port object>, <Port object>]
    """
    LOG.debug("Searching for ports bound to hosts: %s", host_filters)

    # Query PortBinding objects for each host (more efficient than fetching all ports)
    gateway_port_ids: set[str] = set()
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
    gateway_ports: list[port_obj.Port | None] = [
        port_obj.Port.get_object(context, id=port_id) for port_id in gateway_port_ids
    ]
    # Filter out any None values (in case a port was deleted between queries)
    filtered_ports: list[port_obj.Port] = [p for p in gateway_ports if p is not None]

    if not filtered_ports:
        raise Exception(
            f"No ports found bound to gateway hosts (searched for: {host_filters})"
        )

    LOG.debug("Found %d port(s) bound to gateway host", len(filtered_ports))
    return filtered_ports


def _find_trunk_by_port_ids(context, port_ids: list[str], gateway_host: str) -> str:
    """Find trunk whose parent port is in the given port IDs.

    Args:
        context: Neutron context
        port_ids: List of port IDs to check
        gateway_host: Gateway hostname for logging

    Returns:
        Trunk UUID

    Raises:
        Exception: If no matching trunk found

    Example:
        >>> _find_trunk_by_port_ids(ctx, ['port-123', 'port-456'], 'network-node-01')
        '2e558202-0bd0-4971-a9f8-61d1adea0427'
    """
    trunks: list[trunk_obj.Trunk] = trunk_obj.Trunk.get_objects(context)

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


def fetch_network_node_trunk_id() -> str:
    """Dynamically discover the network node trunk ID via OVN Gateway agent.

    This function discovers the network node trunk by:
    1. Finding alive OVN Controller Gateway agents
    2. Getting the host of the gateway agent
    3. Resolving to both hostname and UUID via Ironic (handles both directions)
    4. Querying ports bound to either hostname or UUID
    5. Finding trunks that use those ports as parent ports

    The network node trunk is used to connect router networks to the
    network node (OVN gateway) by adding subports for each VLAN.

    Note: We need both hostname and UUID because some ports may be bound
    using hostname while others use UUID in their binding_host_id.

    Returns:
        The UUID of the network node trunk

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
    gateway_host: str = _get_gateway_agent_host(core_plugin, context)

    # Step 2: Resolve gateway host
    gateway_host, gateway_node_uuid = _resolve_gateway_host(gateway_host)

    # Step 3: Build host filters (both hostname and UUID if applicable)
    host_filters: list[str] = [gateway_host]
    if gateway_node_uuid:
        host_filters.append(gateway_node_uuid)

    # Step 4: Find ports bound to gateway host
    gateway_ports: list[port_obj.Port] = _find_ports_bound_to_hosts(
        context, host_filters
    )

    # Step 5: Find trunk using gateway ports
    gateway_port_ids: list[str] = [port.id for port in gateway_ports]
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
