"""Inspect interface for PAN-OS (Palo Alto) appliances."""

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
        try:
            _discover_and_update_ports(task, client)
        except Exception as e:
            LOG.warning(
                "[node:%s] Could not discover ports via LLDP: %s",
                node.uuid,
                e,
                exc_info=True,
            )
            # Don't fail inspect if port discovery fails

        # TODO: show high-availability all, recording the HA peer serial in
        # extra["mate_serial"] (which enroll-fw also sets) when HA is enabled.

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
    # Sort ports by interface number
    # - If exactly 2 ports: lowest is "outside", highest is "inside"
    # - If 3+ ports: first two in sorted order get "outside"/"inside", rest get None
    def _extract_interface_number(iface_name: str) -> int:
        """Extract numeric part from interface name like 'ethernet1/1' -> 1."""
        try:
            return int(iface_name.split("/")[-1])
        except (ValueError, IndexError):
            return 999  # Put unparsable interfaces at the end

    sorted_ports = sorted(
        inspected_ports, key=lambda p: _extract_interface_number(p.name)
    )
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
