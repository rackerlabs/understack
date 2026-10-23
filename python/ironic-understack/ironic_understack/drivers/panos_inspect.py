"""Inspect interface for PAN-OS (Palo Alto) appliances."""

import time
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
            LOG.debug("[node:%s] Logged in to %s", node.uuid, address)
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

    This temporarily enables LLDP on unconfigured interfaces, collects neighbors,
    then restores the original configuration.
    """
    node = task.node

    # Step 1: Get current interface configuration to determine what needs LLDP
    configured_interfaces = _get_configured_interfaces(client)
    LOG.debug(
        "[node:%s] Found %d configured interfaces",
        node.uuid,
        len(configured_interfaces),
    )

    # Step 2: Get all physical interfaces based on model
    model = node.properties.get("model", "PA-1410")
    all_interfaces = _get_all_physical_interfaces(model)
    interfaces_to_configure = [
        iface for iface in all_interfaces if iface not in configured_interfaces
    ]

    if not interfaces_to_configure:
        LOG.info(
            "[node:%s] All interfaces configured, skipping temporary LLDP setup",
            node.uuid,
        )
        # Still collect whatever LLDP is already there
        interface_macs = client.get_interface_macs()
        lldp_neighbors = client.get_lldp_neighbors()
        _update_ports_from_neighbors(task, lldp_neighbors, interface_macs)
        return

    LOG.debug(
        "[node:%s] Will configure LLDP on %d unconfigured interfaces",
        node.uuid,
        len(interfaces_to_configure),
    )

    # Step 3: Enable LLDP and configure unconfigured interfaces
    _enable_lldp_discovery(client, interfaces_to_configure)

    # Step 4: Wait for LLDP neighbors
    LOG.debug("[node:%s] Waiting 30s for LLDP neighbor discovery", node.uuid)
    time.sleep(30)

    # Step 5: Collect interface MACs and LLDP neighbors
    interface_macs = client.get_interface_macs()
    lldp_neighbors = client.get_lldp_neighbors()
    LOG.info("[node:%s] Discovered %d LLDP neighbors", node.uuid, len(lldp_neighbors))

    # Step 6: Restore original configuration
    _restore_interface_config(client, interfaces_to_configure)

    # Step 7: Update Ironic ports
    _update_ports_from_neighbors(task, lldp_neighbors, interface_macs)


def _get_configured_interfaces(client: panos_api.PanosClient) -> set[str]:
    """Get set of interfaces that have any configuration."""
    configured = set()

    # Check ethernet interface config
    try:
        xpath = (
            "/config/devices/entry[@name='localhost.localdomain']"
            "/network/interface/ethernet"
        )
        result = client.config("get", xpath)

        # Parse XML result
        for entry in result.findall(".//entry"):
            name = entry.get("name")
            if name and any(
                entry.find(tag) is not None
                for tag in [
                    "layer3",
                    "layer2",
                    "tap",
                    "ha",
                    "aggregate-ethernet",
                    "virtual-wire",
                ]
            ):
                configured.add(name)
    except panos_api.PanosApiError as e:
        LOG.warning("Could not check interface configuration: %s", e)

    # Check virtual-wire configurations
    try:
        xpath = (
            "/config/devices/entry[@name='localhost.localdomain']/network/virtual-wire"
        )
        result = client.config("get", xpath)

        for entry in result.findall(".//entry"):
            for tag in ["interface1", "interface2"]:
                iface = entry.findtext(tag)
                if iface:
                    configured.add(iface)
    except panos_api.PanosApiError as e:
        LOG.debug("Could not check virtual-wire configuration: %s", e)

    return configured


def _get_all_physical_interfaces(model: str) -> list[str]:
    """Get list of all physical ethernet interfaces based on model."""
    if "1410" in model:
        return [f"ethernet1/{i}" for i in range(1, 23)]  # PA-1410 has 22 ports
    # Default to 22 ports for unknown models
    return [f"ethernet1/{i}" for i in range(1, 23)]


def _enable_lldp_discovery(
    client: panos_api.PanosClient, interfaces: list[str]
) -> None:
    """Enable LLDP globally and configure it on specified interfaces."""
    # Remove factory default config that blocks interface configuration
    # Must delete zones first (they reference virtual-wires)
    try:
        xpath = (
            "/config/devices/entry[@name='localhost.localdomain']"
            "/vsys/entry[@name='vsys1']/zone"
        )
        client.config("delete", xpath, None)
    except Exception as e:
        LOG.debug("No zone config to remove: %s", e)

    try:
        xpath = (
            "/config/devices/entry[@name='localhost.localdomain']"
            "/network/virtual-wire"
        )
        client.config("delete", xpath, None)
    except Exception as e:
        LOG.debug("No virtual-wire config to remove: %s", e)

    # Commit factory default cleanup
    job_id = client.commit("Inspect: Remove factory default config")
    if job_id:
        client.wait_for_commit(job_id)

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
    if job_id:
        client.wait_for_commit(job_id)

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
    if job_id:
        client.wait_for_commit(job_id)


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
    if job_id:
        client.wait_for_commit(job_id)


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

    # Now create or update ports
    for inspected_port in inspected_ports:
        mac_address = inspected_port.mac_address
        neighbor = neighbor_by_mac[mac_address.lower()]
        local_interface = inspected_port.name

        physical_network = vlan_group_mapping.get(neighbor["system_name"])
        port_name = f"{node.name}:{local_interface}"

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
            port_obj.pxe_enabled = True
            port_obj.create()
            LOG.info(
                "[node:%s] Created port %s (%s)", node.uuid, port_name, mac_address
            )
