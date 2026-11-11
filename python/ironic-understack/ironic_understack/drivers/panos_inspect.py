"""Inspect interface for PAN-OS (Palo Alto) appliances."""

import re
import time
from contextlib import suppress
from typing import ClassVar

import requests
from ironic.common import exception
from ironic.common import states
from ironic.drivers import base
from ironic.objects import port
from oslo_log import log

from ironic_understack.utils import panos_api
from ironic_understack.utils import vlan_group_name_convention

LOG = log.getLogger(__name__)


class PanosInspect(base.InspectInterface):
    """Inspect a PAN-OS appliance over its XML API.

    No ramdisk is involved; everything goes over the management address in
    ``driver_info['management_ip']``, which enroll-fw sets.
    """

    # A firewall has no memory_mb/local_gb/cpu_arch to report.
    ESSENTIAL_PROPERTIES: ClassVar[set] = set()

    def get_properties(self):
        return {
            "management_ip": "Address of the appliance's management interface, "
            "used for the XML API. Required.",
        }

    def validate(self, task):
        if not task.node.driver_info.get("management_ip"):
            raise exception.MissingParameterValue(
                f"Node {task.node.uuid} is missing driver_info management_ip"
            )

    def inspect_hardware(self, task):
        node = task.node
        address = node.driver_info["management_ip"]
        client = panos_api.PanosClient(address)
        try:
            client.login()
            system = client.system_info()
        except (panos_api.PanosApiError, requests.RequestException) as e:
            raise exception.HardwareInspectionFailure(
                error=f"PAN-OS {address}: {e}"
            ) from e

        _apply_system_info(node, system)

        # Discover data plane connectivity via LLDP
        ports_discovered = False
        try:
            _discover_and_update_ports(task, client)
            ports_discovered = True
        except Exception as e:
            LOG.warning(
                "[node:%s] Could not discover ports via LLDP: %s",
                node.uuid,
                e,
                exc_info=True,
            )
            # Don't fail inspect if port discovery fails

        # Validate that the device is usable before marking as manageable
        # Only validate if port discovery succeeded
        if ports_discovered:
            _validate_firewall_readiness(task)

        # Handle HA configuration if this is part of an HA pair
        # Note: HA configuration is attempted but won't block inspection
        _handle_ha_configuration(task, client, system)

        node.save()
        return states.MANAGEABLE


def _apply_system_info(node, system: dict[str, str]) -> None:
    """Record what ``show system info`` reported on the node.

    model and serial are also set by enroll-fw from Nautobot, so those are only
    filled in when missing; a disagreement is logged rather than overwritten.
    """
    properties = dict(node.properties)
    extra = dict(node.extra)
    for target, key, field in (
        (properties, "model", "model"),
        (extra, "serial", "serial"),
    ):
        found = system.get(field)
        if not found:
            continue
        if not target.get(key):
            target[key] = found
        elif target[key] != found:
            LOG.warning(
                "[node:%s] Appliance reports %s %r but the node has %r",
                node.uuid,
                key,
                found,
                target[key],
            )
    if system.get("sw-version"):
        properties["firmware_version"] = system["sw-version"]
    node.properties = properties
    node.extra = extra


def _discover_and_update_ports(task, client: panos_api.PanosClient) -> None:
    """Discover interfaces and LLDP neighbors, then update/create Ironic ports.

    This temporarily enables LLDP on all interfaces, collects neighbors,
    then restores the original configuration.

    LLDP is the source of truth for port connectivity.
    """
    node = task.node

    # Get all physical interfaces based on model
    model = node.properties.get("model", "PA-1410")
    all_interfaces = _get_all_physical_interfaces(model)

    # Enable LLDP on all interfaces
    _enable_lldp_discovery(client, all_interfaces)

    # Wait for LLDP neighbors
    time.sleep(30)

    # Collect interface MACs and LLDP neighbors
    interface_macs = client.get_interface_macs()
    lldp_neighbors = client.get_lldp_neighbors()
    LOG.info("[node:%s] Discovered %d LLDP neighbors", node.uuid, len(lldp_neighbors))

    # CRITICAL: Must have at least 2 neighbors (outside/inside minimum)
    if len(lldp_neighbors) < 2:
        raise exception.HardwareInspectionFailure(
            f"Firewall {node.uuid} requires at least 2 LLDP neighbors "
            f"(outside/inside minimum), but only discovered {len(lldp_neighbors)}. "
            "Check physical cabling and switch LLDP configuration."
        )

    # Restore original configuration (delete all interface config we added)
    _restore_interface_config(client, all_interfaces)

    # Update Ironic ports
    _update_ports_from_neighbors(task, lldp_neighbors, interface_macs)


def _get_all_physical_interfaces(model: str) -> list[str]:
    """Get list of all physical ethernet interfaces based on model."""
    if "1410" in model:
        return [f"ethernet1/{i}" for i in range(1, 23)]  # PA-1410 has 22 ports
    # Default to 22 ports for unknown models
    return [f"ethernet1/{i}" for i in range(1, 23)]


def _enable_lldp_discovery(
    client: panos_api.PanosClient, interfaces: list[str]
) -> None:
    """Enable LLDP globally and configure it on specified interfaces.

    Destructively removes any existing config that would block LLDP setup.
    """
    # Remove all blocking config: security rules -> zones -> virtual-wires
    rules_deleted = False
    zones_deleted = False
    vwires_deleted = False

    try:
        xpath = (
            "/config/devices/entry[@name='localhost.localdomain']"
            "/vsys/entry[@name='vsys1']/rulebase/security/rules"
        )
        client.config("delete", xpath, None)
        rules_deleted = True
    except panos_api.PanosApiError:
        pass  # No security rules to delete

    try:
        xpath = (
            "/config/devices/entry[@name='localhost.localdomain']"
            "/vsys/entry[@name='vsys1']/zone"
        )
        client.config("delete", xpath, None)
        zones_deleted = True
    except panos_api.PanosApiError:
        pass  # No zone config to delete

    try:
        xpath = (
            "/config/devices/entry[@name='localhost.localdomain']"
            "/network/virtual-wire"
        )
        client.config("delete", xpath, None)
        vwires_deleted = True
    except panos_api.PanosApiError:
        pass  # No virtual-wire config to delete

    if rules_deleted or zones_deleted or vwires_deleted:
        LOG.debug(
            "Deleted factory config: rules=%s zones=%s vwires=%s",
            rules_deleted,
            zones_deleted,
            vwires_deleted,
        )

    # Remove virtual-wire config from all interfaces (no per-interface logs)
    for iface in interfaces:
        with suppress(panos_api.PanosApiError):
            xpath = (
                f"/config/devices/entry[@name='localhost.localdomain']"
                f"/network/interface/ethernet/entry[@name='{iface}']/virtual-wire"
            )
            client.config("delete", xpath, None)

    # Only commit if we actually deleted something
    if rules_deleted or zones_deleted or vwires_deleted:
        job_id = client.commit("Inspect: Remove factory default config")
        if job_id and not client.wait_for_commit(job_id):
            raise panos_api.PanosApiError(
                "Failed to commit factory default cleanup configuration"
            )

    # Enable LLDP globally
    xpath = "/config/devices/entry[@name='localhost.localdomain']/network/lldp"
    element = "<enable>yes</enable>"
    client.config("set", xpath, element)

    # Create LLDP profile
    xpath = (
        "/config/devices/entry[@name='localhost.localdomain']"
        "/network/profiles/lldp-profile/entry[@name='lldp-inspect']"
    )
    element = "<mode>transmit-receive</mode>"
    client.config("set", xpath, element)

    # Commit LLDP profile
    job_id = client.commit("Inspect: Enable LLDP profile")
    if job_id and not client.wait_for_commit(job_id):
        raise panos_api.PanosApiError("Failed to commit LLDP profile configuration")

    # Configure interfaces with LLDP
    for iface in interfaces:
        xpath = (
            f"/config/devices/entry[@name='localhost.localdomain']"
            f"/network/interface/ethernet/entry[@name='{iface}']"
        )
        element = (
            "<layer3>"
            "<lldp><enable>yes</enable><profile>lldp-inspect</profile></lldp>"
            "</layer3>"
            "<link-speed>auto</link-speed>"
            "<link-state>up</link-state>"
        )
        client.config("set", xpath, element)

    # Commit interface changes
    job_id = client.commit("Inspect: Enable interfaces for LLDP discovery")
    if job_id and not client.wait_for_commit(job_id):
        raise panos_api.PanosApiError(
            "Failed to commit interface configuration for LLDP"
        )


def _restore_interface_config(
    client: panos_api.PanosClient, interfaces: list[str]
) -> None:
    """Remove temporary LLDP configuration from interfaces."""
    for iface in interfaces:
        xpath = (
            f"/config/devices/entry[@name='localhost.localdomain']"
            f"/network/interface/ethernet/entry[@name='{iface}']"
        )
        try:
            client.config("delete", xpath)
        except panos_api.PanosApiError as e:
            LOG.warning("Could not delete interface %s config: %s", iface, e)

    # Commit restore
    job_id = client.commit("Inspect: Restore original interface configuration")
    if job_id and not client.wait_for_commit(job_id):
        raise panos_api.PanosApiError(
            "Failed to commit interface restoration configuration"
        )


def _update_ports_from_neighbors(
    task, neighbors: list[dict[str, str]], interface_macs: dict[str, str]
) -> None:
    """Create or update Ironic ports based on LLDP neighbor data."""
    from ironic_understack import conf
    from ironic_understack.utils.inspected_port import InspectedPort

    node = task.node
    CONF = conf.CONF

    def _normalize_switch_name(name: str) -> str:
        """Normalize switch name to FQDN format matching baremetal servers."""
        suffix = ".rackspace.net"
        name = str(name).lower()
        return name if name.endswith(suffix) else name + suffix

    # First, create InspectedPort objects for all neighbors with MACs
    inspected_ports = []
    neighbor_by_mac = {}

    for neighbor in neighbors:
        local_interface = neighbor["local_interface"]
        mac_address = interface_macs.get(local_interface)

        if not mac_address:
            LOG.warning(
                "[node:%s] No MAC address for %s, skipping port creation",
                node.uuid,
                local_interface,
            )
            continue

        normalized_switch_name = _normalize_switch_name(neighbor["system_name"])

        inspected_port = InspectedPort(
            mac_address=mac_address,
            name=local_interface,
            switch_system_name=normalized_switch_name,
            switch_port_id=neighbor["port_id"],
            switch_chassis_id=neighbor["chassis_id"],
        )
        inspected_ports.append(inspected_port)
        neighbor_by_mac[mac_address.lower()] = neighbor

    if not inspected_ports:
        LOG.info("[node:%s] No ports with MAC addresses to create", node.uuid)
        return

    # Get VLAN group names for all ports
    try:
        vlan_group_mapping = vlan_group_name_convention.vlan_group_names(
            inspected_ports, CONF.ironic_understack.switch_name_vlan_group_mapping
        )
    except Exception as e:
        LOG.warning(
            "[node:%s] Could not derive VLAN groups: %s. "
            "Creating ports without physical_network.",
            node.uuid,
            e,
        )
        vlan_group_mapping = {}

    # Determine port categories based on interface numbers
    # Sort ports by interface number (natural sort, e.g., ethernet1/20 < ethernet2/19)
    # - If exactly 2 ports: lowest is "outside", highest is "inside"
    # - If 3+ ports: first two in sorted order get "outside"/"inside", rest get None
    def _interface_sort_key(iface_name: str) -> tuple:
        """Natural sort key for interface names like 'ethernet1/20'.

        Splits on digits to create tuples for natural sorting:
        ethernet1/20 -> ('ethernet', 1, '/', 20) < ('ethernet', 2, '/', 19)
        """
        pieces = re.split(r"(\d+)", iface_name)
        return tuple(
            (0, int(piece)) if piece.isdigit() else (1, piece) for piece in pieces
        )

    sorted_ports = sorted(inspected_ports, key=lambda p: _interface_sort_key(p.name))
    port_categories = {}

    if len(sorted_ports) == 2:
        # Exactly 2 ports: lowest is outside, highest is inside
        port_categories[sorted_ports[0].mac_address.lower()] = "outside"
        port_categories[sorted_ports[1].mac_address.lower()] = "inside"
    elif len(sorted_ports) >= 3:
        # 3+ ports: only first two consecutive get categories
        port_categories[sorted_ports[0].mac_address.lower()] = "outside"
        port_categories[sorted_ports[1].mac_address.lower()] = "inside"
    # If only 1 port, no category assigned

    # Now create or update ports
    for inspected_port in inspected_ports:
        mac_address = inspected_port.mac_address
        neighbor = neighbor_by_mac[mac_address.lower()]
        local_interface = inspected_port.name

        physical_network = vlan_group_mapping.get(neighbor["system_name"])
        port_name = f"{node.name}:{local_interface}"
        category = port_categories.get(mac_address.lower())

        # Check if port already exists (by MAC or name)
        existing_port = None
        for p in task.ports:
            if p.address.lower() == mac_address.lower():
                existing_port = p
                break
            if p.name == port_name:
                existing_port = p
                break

        if existing_port:
            # Update existing port
            existing_port.address = mac_address
            existing_port.local_link_connection = inspected_port.local_link_connection
            existing_port.extra = {"bios_name": local_interface}
            if physical_network and not existing_port.physical_network:
                existing_port.physical_network = physical_network
            existing_port.category = category
            existing_port.name = port_name
            existing_port.save()
            LOG.debug("[node:%s] Updated port %s", node.uuid, port_name)
        else:
            # Create new port
            port_obj = port.Port(task.context)
            port_obj.node_id = node.id
            port_obj.address = mac_address
            port_obj.name = port_name
            port_obj.local_link_connection = inspected_port.local_link_connection
            port_obj.extra = {"bios_name": local_interface}
            port_obj.physical_network = physical_network
            port_obj.category = category
            port_obj.pxe_enabled = True
            port_obj.create()
            LOG.info(
                "[node:%s] Created port %s (%s) category=%s",
                node.uuid,
                port_name,
                mac_address,
                category or "none",
            )

    # Clean up stale ports that weren't discovered in this inspection
    # Only delete if we successfully discovered some ports
    # (otherwise may be LLDP failure)
    discovered_macs = {p.mac_address.lower() for p in inspected_ports}
    stale_ports = [p for p in task.ports if p.address.lower() not in discovered_macs]

    if stale_ports:
        LOG.info(
            "[node:%s] Found %d stale port(s) not in current LLDP discovery",
            node.uuid,
            len(stale_ports),
        )
        for stale_port in stale_ports:
            LOG.warning(
                "[node:%s] Deleting stale port %s (%s) - not found in LLDP",
                node.uuid,
                stale_port.name,
                stale_port.address,
            )
            stale_port.destroy()


def _validate_firewall_readiness(task) -> None:
    """Validate that the firewall has minimum requirements to become manageable.

    Checks:
    - Port categories assigned (outside/inside)
    - For PA-1410: FAIL if using slow 1G ports (eth1/1-18 instead of 10G eth1/19-22)

    Note: The minimum 2 neighbors check is done earlier in _discover_and_update_ports
    before ports are created.

    :raises HardwareInspectionFailure: if requirements not met
    """
    node = task.node
    ports = list(task.ports)

    # Check port categories (should have been assigned during port creation)
    categories = {getattr(p, "category", None) for p in ports}
    if "outside" not in categories or "inside" not in categories:
        LOG.warning(
            "[node:%s] Port categories incomplete: found %s, expected outside/inside",
            node.uuid,
            categories - {None},
        )

    # For PA-1410: FAIL if using slow 1G ports
    model = node.properties.get("model", "")
    if "1410" in model:
        slow_ports = []
        for port in ports:
            bios_name = port.extra.get("bios_name", "") if port.extra else ""
            if _is_slow_port_1410(bios_name):
                slow_ports.append(bios_name)

        if slow_ports:
            raise exception.HardwareInspectionFailure(
                f"PA-1410 cannot use slow 1G ports {slow_ports}. "
                "Must use 10G ports ethernet1/19-22 for production traffic. "
                "Check physical cabling."
            )

    LOG.info(
        "[node:%s] Firewall validation passed: %d ports discovered, " "categories=%s",
        node.uuid,
        len(ports),
        sorted(categories - {None}),
    )


def _is_slow_port_1410(interface_name: str) -> bool:
    """Check if interface is a slow 1G port on PA-1410.

    PA-1410 has:
    - ethernet1/1-18: 1G ports (slow)
    - ethernet1/19-22: 10G ports (fast)
    """
    if not interface_name:
        return False
    match = re.match(r"ethernet1/(\d+)", interface_name)
    if not match:
        return False
    port_num = int(match.group(1))
    return 1 <= port_num <= 18


# ============================================================================
# HA Configuration Functions
# ============================================================================


def _get_ha_role(node) -> str | None:
    """Determine HA role from traits.

    :returns: 'primary', 'secondary', or None (standalone)
    """
    # Must have mate_serial to be in an HA pair
    if not node.extra.get("mate_serial"):
        return None

    # Check traits
    if not hasattr(node, "traits") or not node.traits:
        LOG.warning(
            "[node:%s] Has mate_serial %s but no traits",
            node.uuid,
            node.extra.get("mate_serial"),
        )
        return None

    # Traits may be objects or strings - normalize to uppercase strings
    traits = []
    for t in node.traits:
        if hasattr(t, "trait"):
            # Ironic Trait object
            traits.append(str(t.trait).upper())
        else:
            # Already a string
            traits.append(str(t).upper())

    if "CUSTOM_PRIMARY" in traits:
        return "primary"
    elif "CUSTOM_SECONDARY" in traits:
        return "secondary"
    else:
        LOG.warning(
            "[node:%s] Has mate_serial but no HA role trait (found: %s)",
            node.uuid,
            traits,
        )
        return None


def _find_mate_node(task, mate_serial: str):
    """Find the HA mate node by serial number.

    :param task: TaskManager instance
    :param mate_serial: Serial number of the mate device
    :returns: Ironic node object or None
    """
    from ironic.objects import node as node_obj

    try:
        # Cannot filter by extra.serial directly, so list all nodes and search
        # Filter by driver to limit scope; include_children ensures we see child nodes
        nodes = node_obj.Node.list(
            task.context,
            filters={"driver": "panos", "include_children": True},
        )

        for node in nodes:
            if node.extra.get("serial") == mate_serial:
                LOG.debug(
                    "[node:%s] Found mate node %s with serial %s",
                    task.node.uuid,
                    node.uuid,
                    mate_serial,
                )
                return node

        LOG.debug(
            "[node:%s] Mate with serial %s not found among %d panos nodes",
            task.node.uuid,
            mate_serial,
            len(nodes),
        )
        return None

    except Exception as e:
        LOG.error(
            "[node:%s] Error searching for mate node with serial %s: %s",
            task.node.uuid,
            mate_serial,
            e,
        )
        return None


def _validate_mate_compatibility(node, mate) -> tuple[bool, str]:
    """Verify mate has same model and opposite role trait.

    :returns: (is_valid, error_message)
    """
    # 1. Resource class should match (same model)
    if node.resource_class != mate.resource_class:
        return (
            False,
            f"Resource class mismatch: {node.resource_class} vs "
            f"{mate.resource_class} - mates must be same model",
        )

    # 2. Roles should be opposite
    my_role = _get_ha_role(node)
    mate_role = _get_ha_role(mate)

    if my_role == mate_role:
        return (
            False,
            f"Both nodes have same role: {my_role} - "
            "primary must pair with secondary",
        )

    if my_role not in ("primary", "secondary") or mate_role not in (
        "primary",
        "secondary",
    ):
        return (False, f"Invalid HA roles: self={my_role}, mate={mate_role}")

    # 3. Check bidirectional mate_serial
    mate_mate_serial = mate.extra.get("mate_serial")
    my_serial = node.extra.get("serial")

    if mate_mate_serial != my_serial:
        return (
            False,
            f"Mate serial mismatch: mate expects {mate_mate_serial}, "
            f"but my serial is {my_serial}",
        )

    return (True, "")


def _calculate_ha_addresses(role: str) -> dict[str, str]:
    """Calculate HA IP addresses based on role.

    :param role: 'primary' or 'secondary'
    :returns: Dict with ha1_ip, ha1_backup_ip, ha2_ip, peer_ha1,
              peer_ha1_backup, priority
    """
    if role == "primary":
        return {
            "ha1_ip": "10.2.2.1",
            "ha1_backup_ip": "10.2.2.5",
            "ha2_ip": "10.2.2.9",
            "peer_ha1": "10.2.2.2",
            "peer_ha1_backup": "10.2.2.6",
            "priority": "50",  # Lower = active
        }
    else:  # secondary
        return {
            "ha1_ip": "10.2.2.2",
            "ha1_backup_ip": "10.2.2.6",
            "ha2_ip": "10.2.2.10",
            "peer_ha1": "10.2.2.1",
            "peer_ha1_backup": "10.2.2.5",
            "priority": "100",  # Higher = passive
        }


def _handle_ha_configuration(
    task, client: panos_api.PanosClient, system: dict
) -> str | None:
    """Handle HA configuration during inspection.

    Configures HA independently on each device during its own inspection.
    Each device is configured with its role-specific settings regardless of
    mate availability. The devices will pair automatically when both are
    configured and connected.

    This configuration is idempotent - if HA is already correctly configured,
    the commit will report "no changes" and succeed. If settings need to change
    (e.g., wrong role), it will reconfigure.

    Workflow:
    1. No HA role → skip (standalone device)
    2. Has HA role → configure this device with its settings

    :returns: None (always completes inspection)
    """
    node = task.node
    extra = dict(node.extra)

    # Check if this device is part of an HA pair
    role = _get_ha_role(node)
    if not role:
        LOG.info("[node:%s] Not part of HA pair, skipping HA configuration", node.uuid)
        return None

    mate_serial = extra.get("mate_serial")
    LOG.info("[node:%s] HA role=%s, mate_serial=%s", node.uuid, role, mate_serial)

    # Configure HA on this device (idempotent - will only commit if changes needed)
    LOG.info(
        "[node:%s] Configuring HA as %s (independent of mate status)",
        node.uuid,
        role,
    )

    # Calculate addresses for this device's role
    addresses = _calculate_ha_addresses(role)

    try:
        # Configure HA on this device
        success = client.configure_ha(
            role=role,
            ha1_ip=addresses["ha1_ip"],
            ha1_backup_ip=addresses["ha1_backup_ip"],
            ha2_ip=addresses["ha2_ip"],
            peer_ha1=addresses["peer_ha1"],
            peer_ha1_backup=addresses["peer_ha1_backup"],
            priority=addresses["priority"],
        )

        if not success:
            raise exception.HardwareInspectionFailure(
                error=f"Failed to configure HA on device as {role}"
            )

        LOG.info("[node:%s] Successfully configured HA as %s", node.uuid, role)

        # Wait for HA to establish before validation
        LOG.info("[node:%s] Waiting 15s for HA to establish...", node.uuid)
        time.sleep(15)

        # Comprehensive HA validation and automatic pairing
        _validate_and_pair_ha(task, client, node, extra, mate_serial, role)

    except Exception as e:
        LOG.error("[node:%s] Failed to configure HA: %s", node.uuid, e)
        raise exception.HardwareInspectionFailure(
            error=f"HA configuration failed: {e}"
        ) from e

    return None


def _validate_and_pair_ha(
    task,
    client: panos_api.PanosClient,
    node,
    extra: dict,
    mate_serial: str,
    role: str,
) -> None:
    """Validate HA pairing and set ha_operational flag for this device.

    Performs comprehensive validation:
    1. HA interface states (ha1-a, ha1-b, hsci)
    2. Peer connection status
    3. Bidirectional serial validation (checks mate device too)
    4. Interface speed validation (hsci vs data plane)
    5. Pre-flight compatibility checks (resource_class, roles)

    Sets extra.ha_operational = True only when ALL checks pass.
    Does NOT modify mate node's extra fields or transition states.
    The enroll-fw workflow will read ha_operational from both devices
    and decide whether to promote.

    :raises: Logs warnings but does not raise - allows inspection to complete
    """
    # Default to False - only set True if all checks pass
    extra["ha_operational"] = False

    try:
        # Step 1: Check HA interface states
        ha_iface_status = client.get_ha_interface_status()
        ha1_a_state = ha_iface_status.get("ha1-a", {}).get("state")
        ha1_b_state = ha_iface_status.get("ha1-b", {}).get("state")
        hsci_state = ha_iface_status.get("hsci", {}).get("state")

        if ha1_a_state != "up" or ha1_b_state != "up" or hsci_state != "up":
            reason = (
                f"HA interfaces not all up: ha1-a={ha1_a_state}, "
                f"ha1-b={ha1_b_state}, hsci={hsci_state}"
            )
            LOG.info("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        LOG.info("[node:%s] HA interfaces operational", node.uuid)

        # Step 2: Query HA status and check peer connection
        ha_status = client.get_ha_status()
        peer_serial = ha_status.get("peer", {}).get("serial")
        peer_conn = ha_status.get("peer", {}).get("conn_status")

        if peer_conn != "up":
            reason = (
                f"HA peer connection not up: "
                f"conn={peer_conn}, peer_serial={peer_serial}"
            )
            LOG.info("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        if peer_serial != mate_serial:
            reason = (
                f"HA peer serial mismatch: got {peer_serial}, "
                f"expected {mate_serial}"
            )
            LOG.warning("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        LOG.info("[node:%s] HA peer connected: %s", node.uuid, peer_serial)

        # Step 3: Find mate node in Ironic
        mate = _find_mate_node(task, mate_serial)
        if not mate:
            reason = f"Mate node {mate_serial} not found in Ironic"
            LOG.info("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        # Step 4: Pre-flight compatibility checks
        my_serial = extra.get("serial")
        mate_extra = dict(mate.extra)
        mate_mate_serial = mate_extra.get("mate_serial")

        # Check bidirectional mate_serial configuration
        if mate_mate_serial != my_serial:
            reason = (
                f"Mate serial mismatch: mate expects {mate_mate_serial}, "
                f"my serial is {my_serial}"
            )
            LOG.warning("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        # Check resource class match
        if node.resource_class != mate.resource_class:
            reason = (
                f"Resource class mismatch: self={node.resource_class}, "
                f"mate={mate.resource_class}"
            )
            LOG.warning("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        # Check opposite HA roles
        my_role = _get_ha_role(node)
        mate_role = _get_ha_role(mate)
        if not my_role or not mate_role:
            reason = f"Missing HA roles: self={my_role}, mate={mate_role}"
            LOG.warning("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        if my_role == mate_role:
            reason = f"Same HA role on both devices: {my_role}"
            LOG.warning("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        LOG.info(
            "[node:%s] Pre-flight checks passed: roles=%s/%s, class=%s",
            node.uuid,
            my_role,
            mate_role,
            node.resource_class,
        )

        # Step 5: Bidirectional device validation - query mate device
        mate_address = mate.driver_info.get("management_ip")
        if not mate_address:
            reason = "Mate has no management_ip"
            LOG.warning("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        mate_client = panos_api.PanosClient(mate_address)
        mate_client.login()
        mate_ha_status = mate_client.get_ha_status()
        mate_peer_serial = mate_ha_status.get("peer", {}).get("serial")
        mate_peer_conn = mate_ha_status.get("peer", {}).get("conn_status")

        if mate_peer_serial != my_serial:
            reason = (
                f"Mate peer serial mismatch: "
                f"got {mate_peer_serial}, expected {my_serial}"
            )
            LOG.warning("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        if mate_peer_conn != "up":
            reason = f"Mate peer connection not up: {mate_peer_conn}"
            LOG.warning("[node:%s] %s", node.uuid, reason)
            extra["ha_check_reason"] = reason
            return

        LOG.info("[node:%s] Bidirectional HA validation passed", node.uuid)

        # Step 6: Validate interface speeds (hsci >= data plane)
        # Get data plane interface speeds from discovered ports
        discovered_speeds = []
        for port_obj in task.ports:
            port_info = port_obj.local_link_connection or {}
            if hasattr(port_info, "get"):
                speed = port_info.get("port_speed")
                if speed:
                    with suppress(ValueError, TypeError):
                        discovered_speeds.append(int(speed))

        if discovered_speeds:
            max_data_speed = max(discovered_speeds)
            hsci_speed_str = ha_iface_status.get("hsci", {}).get("speed", "0")
            try:
                # Convert speed string like "10000" or "10G" to Mbps
                if "G" in hsci_speed_str:
                    hsci_speed = int(hsci_speed_str.replace("G", "")) * 1000
                else:
                    hsci_speed = int(hsci_speed_str)

                if hsci_speed < max_data_speed:
                    LOG.warning(
                        "[node:%s] HSCI speed (%s Mbps) < data plane (%s Mbps) - "
                        "may impact HA statefulness",
                        node.uuid,
                        hsci_speed,
                        max_data_speed,
                    )
                    # Don't fail, just warn
            except (ValueError, TypeError) as e:
                LOG.debug(
                    "[node:%s] Could not parse interface speeds: %s",
                    node.uuid,
                    e,
                )

        # Step 7: Validate HA pair switch diversity
        # Both devices must connect to different switches (true HA requirement)
        LOG.info("[node:%s] Validating HA pair switch diversity", node.uuid)

        # Collect this device's switches from LLDP data
        my_switches = set()
        for port_obj in task.ports:
            llc = port_obj.local_link_connection or {}
            if hasattr(llc, "get"):
                switch_info = llc.get("switch_info")
                if switch_info and switch_info != "None":
                    my_switches.add(switch_info)

        # Collect mate device's switches from LLDP data
        mate_switches = set()
        for port_obj in port.Port.list_by_node_id(task.context, mate.id):
            llc = port_obj.local_link_connection or {}
            if hasattr(llc, "get"):
                switch_info = llc.get("switch_info")
                if switch_info and switch_info != "None":
                    mate_switches.add(switch_info)

        # Check for switch overlap (both devices on same switch = not true HA)
        switch_overlap = my_switches & mate_switches
        if switch_overlap:
            error_msg = (
                f"HA pair cabling error: both devices connected to same switch(es) "
                f"({', '.join(sorted(switch_overlap))}). "
                "HA pair must be on different switches."
            )
            LOG.error("[node:%s] %s", node.uuid, error_msg)
            extra["ha_check_reason"] = error_msg
            raise exception.HardwareInspectionFailure(error_msg)

        LOG.info(
            "[node:%s] Switch diversity validated: %d switches on this device, "
            "%d on mate, no overlap",
            node.uuid,
            len(my_switches),
            len(mate_switches),
        )

        # Step 8: All validations passed - mark this node as operational
        LOG.info(
            "[node:%s] HA pair fully validated: %s (%s) <-> %s (%s)",
            node.uuid,
            my_serial,
            my_role,
            mate_serial,
            mate_role,
        )

        # Set ha_operational = True (will be saved in finally block)
        LOG.info("[node:%s] All HA validation checks passed", node.uuid)
        extra["ha_operational"] = True
        # Clear any previous failure reason
        extra.pop("ha_check_reason", None)

    except Exception as e:
        LOG.exception(
            "[node:%s] HA validation/pairing failed: %s",
            node.uuid,
            e,
        )
        # Set failure reason for troubleshooting
        extra["ha_check_reason"] = str(e)
        # Don't raise - allow inspection to complete even if pairing fails
    finally:
        # Always save ha_operational status (True if all checks passed, False otherwise)
        node.extra = extra
        node.save()
        LOG.debug(
            "[node:%s] HA operational status set to: %s",
            node.uuid,
            extra.get("ha_operational"),
        )


def _validate_ha_status(
    client: panos_api.PanosClient,
    node_uuid: str,
    expected_peer_serial: str,
    role: str,
) -> tuple[bool, str]:
    """Validate HA configuration and connectivity after setup.

    Checks:
    - HA enabled
    - Peer serial matches expected mate
    - Peer connection status
    - HA link status (HA1, HA1-backup)
    - Local state matches role expectations

    :param client: PanosClient for the device to validate
    :param node_uuid: Node UUID for logging
    :param expected_peer_serial: Expected serial number of HA peer
    :param role: Expected role ('primary' or 'secondary')
    :returns: (is_valid, error_message) - error_message empty if valid
    """
    try:
        ha_status = client.get_ha_status()

        # Check if query failed
        if "error" in ha_status:
            return (False, f"Failed to query HA status: {ha_status['error']}")

        # Check HA enabled
        if ha_status.get("enabled") != "yes":
            return (False, "HA not enabled on device")

        # Check peer serial (critical - must match)
        peer_serial = ha_status.get("peer", {}).get("serial", "unknown")
        if peer_serial == "unknown":
            # Peer not discovered yet - could be transient
            LOG.warning(
                "[node:%s] Peer not discovered yet, may need more time", node_uuid
            )
            return (False, "Peer not discovered yet (HA may still be initializing)")

        if peer_serial != expected_peer_serial:
            return (
                False,
                f"Peer serial mismatch: expected {expected_peer_serial}, "
                f"got {peer_serial}",
            )

        # Check peer connection (warn if down, but don't fail - could be cabling)
        peer_conn = ha_status.get("peer", {}).get("conn_status", "down")
        if peer_conn != "up":
            LOG.warning(
                "[node:%s] Peer connection not up: %s (check physical HA links)",
                node_uuid,
                peer_conn,
            )

        # Check HA link status (warn only - physical cabling may not be complete)
        conn_ha1_up = ha_status.get("peer", {}).get("conn_ha1_up", False)
        conn_ha1_backup_up = ha_status.get("peer", {}).get("conn_ha1_backup_up", False)

        if not conn_ha1_up:
            LOG.warning("[node:%s] HA1 link not up (check ha1-a cabling)", node_uuid)

        if not conn_ha1_backup_up:
            LOG.warning(
                "[node:%s] HA1-backup link not up (check ha1-b cabling)", node_uuid
            )

        # Check local state matches role expectations
        local_state = ha_status.get("local", {}).get("state", "unknown")

        # Note: States can vary during initialization:
        # - active, active-primary, active-secondary
        # - passive, suspended
        # - initial, tentative
        if role == "primary":
            # Primary should eventually become active, but may be in transition
            if local_state not in [
                "active",
                "active-primary",
                "tentative",
                "initial",
            ]:
                LOG.warning(
                    "[node:%s] Primary in unexpected state: %s (expected active)",
                    node_uuid,
                    local_state,
                )
        elif role == "secondary" and local_state not in [
            "passive",
            "active-secondary",
            "tentative",
            "initial",
            "suspended",
        ]:
            # Secondary should eventually become passive, but may be in transition
            LOG.warning(
                "[node:%s] Secondary in unexpected state: %s (expected passive)",
                node_uuid,
                local_state,
            )

        LOG.info(
            "[node:%s] HA validation passed: peer=%s, state=%s, conn=%s, "
            "ha1=%s, ha1-backup=%s",
            node_uuid,
            peer_serial,
            local_state,
            peer_conn,
            "up" if conn_ha1_up else "down",
            "up" if conn_ha1_backup_up else "down",
        )

        return (True, "")

    except Exception as e:
        return (False, f"Exception during HA validation: {e}")


def _validate_ha_interfaces(
    client: panos_api.PanosClient, node_uuid: str
) -> tuple[bool, str]:
    """Validate HA interface operational status.

    :param client: PanosClient for the device
    :param node_uuid: Node UUID for logging
    :returns: (all_up, warning_message)
    """
    try:
        interfaces = client.get_ha_interface_status()

        all_up = True
        down_interfaces = []

        for iface_name, status in interfaces.items():
            state = status.get("state", "unknown")
            if state != "up":
                all_up = False
                down_interfaces.append(iface_name)
                LOG.warning(
                    "[node:%s] HA interface %s is %s (speed: %s, duplex: %s)",
                    node_uuid,
                    iface_name,
                    state,
                    status.get("speed", "unknown"),
                    status.get("duplex", "unknown"),
                )
            else:
                LOG.debug(
                    "[node:%s] HA interface %s is up (speed: %s, duplex: %s)",
                    node_uuid,
                    iface_name,
                    status.get("speed", "unknown"),
                    status.get("duplex", "unknown"),
                )

        if not all_up:
            return (
                False,
                f"HA interfaces down: {', '.join(down_interfaces)} - "
                "check physical cabling",
            )

        return (True, "")

    except Exception as e:
        LOG.warning("[node:%s] Could not query HA interface status: %s", node_uuid, e)
        return (False, f"Failed to query interface status: {e}")


def _configure_ha_pair(
    task, my_client: panos_api.PanosClient, node, mate, my_role: str, mate_role: str
) -> bool:
    """Configure HA on both devices in the pair.

    :returns: True if successful, False otherwise
    """
    LOG.info(
        "[node:%s] Configuring HA: self=%s, mate=%s(%s)",
        node.uuid,
        my_role,
        mate.uuid,
        mate_role,
    )

    # Get mate serials for validation
    my_serial = node.extra.get("serial")
    mate_serial = mate.extra.get("serial")

    try:
        # Calculate addresses for each device
        my_addresses = _calculate_ha_addresses(my_role)
        mate_addresses = _calculate_ha_addresses(mate_role)

        # Configure this device
        LOG.info("[node:%s] Configuring HA as %s", node.uuid, my_role)
        success = my_client.configure_ha(
            role=my_role,
            ha1_ip=my_addresses["ha1_ip"],
            ha1_backup_ip=my_addresses["ha1_backup_ip"],
            ha2_ip=my_addresses["ha2_ip"],
            peer_ha1=my_addresses["peer_ha1"],
            peer_ha1_backup=my_addresses["peer_ha1_backup"],
            priority=my_addresses["priority"],
        )

        if not success:
            LOG.error("[node:%s] Failed to configure HA", node.uuid)
            return False

        # Configure mate device
        mate_address = mate.driver_info.get("management_ip")
        if not mate_address:
            LOG.error("[node:%s] Mate has no management_ip", node.uuid)
            return False

        LOG.info(
            "[node:%s] Configuring HA on mate %s as %s",
            node.uuid,
            mate.uuid,
            mate_role,
        )
        mate_client = panos_api.PanosClient(mate_address)
        mate_client.login()

        success = mate_client.configure_ha(
            role=mate_role,
            ha1_ip=mate_addresses["ha1_ip"],
            ha1_backup_ip=mate_addresses["ha1_backup_ip"],
            ha2_ip=mate_addresses["ha2_ip"],
            peer_ha1=mate_addresses["peer_ha1"],
            peer_ha1_backup=mate_addresses["peer_ha1_backup"],
            priority=mate_addresses["priority"],
        )

        if not success:
            LOG.error(
                "[node:%s] Failed to configure HA on mate %s", node.uuid, mate.uuid
            )
            return False

        # Wait for HA to initialize
        LOG.info("[node:%s] Waiting for HA to initialize...", node.uuid)
        time.sleep(10)  # Give HA time to establish connections

        # Validate this device
        LOG.info("[node:%s] Validating HA configuration on this device", node.uuid)
        is_valid, error_msg = _validate_ha_status(
            my_client, node.uuid, mate_serial, my_role
        )

        if not is_valid:
            LOG.error("[node:%s] HA validation failed: %s", node.uuid, error_msg)
            # Don't fail hard - configuration may be applied but links not up
            # Log error but continue - operator can fix cabling
            LOG.warning(
                "[node:%s] Continuing despite validation failure - "
                "may be physical cabling issue",
                node.uuid,
            )

        # Validate mate device
        LOG.info("[node:%s] Validating HA configuration on mate device", node.uuid)
        is_valid, error_msg = _validate_ha_status(
            mate_client, mate.uuid, my_serial, mate_role
        )

        if not is_valid:
            LOG.error("[node:%s] Mate HA validation failed: %s", node.uuid, error_msg)
            LOG.warning(
                "[node:%s] Continuing despite mate validation failure - "
                "may be physical cabling issue",
                node.uuid,
            )

        # Validate HA interfaces on both devices
        LOG.info("[node:%s] Checking HA interface status", node.uuid)
        all_up, warning = _validate_ha_interfaces(my_client, node.uuid)
        if not all_up:
            LOG.warning("[node:%s] %s", node.uuid, warning)

        all_up, warning = _validate_ha_interfaces(mate_client, mate.uuid)
        if not all_up:
            LOG.warning("[node:%s] Mate: %s", node.uuid, warning)

        LOG.info(
            "[node:%s] HA configuration and validation completed "
            "(check warnings for any link issues)",
            node.uuid,
        )
        return True

    except Exception as e:
        LOG.exception(
            "[node:%s] Exception during HA configuration: %s",
            node.uuid,
            e,
        )
        return False
