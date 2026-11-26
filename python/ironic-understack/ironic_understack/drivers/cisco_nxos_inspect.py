"""Non-destructive inspect interface for Cisco NX-OS switches."""

from typing import ClassVar

import requests
from ironic.common import exception
from ironic.common import states
from ironic.drivers import base
from ironic.drivers.modules import inspect_utils
from ironic.objects import port
from oslo_log import log

from ironic_understack.drivers import cisco_nxos_base
from ironic_understack.drivers import cisco_nxos_firmware
from ironic_understack.drivers.cisco_nxos_base import CiscoNxosInterface
from ironic_understack.utils import nxos_api

LOG = log.getLogger(__name__)

# NX-OS reports ``manufacturer`` in ``show version``; this is the fallback.
MANUFACTURER = "Cisco Systems, Inc."


class CiscoNxosInspect(CiscoNxosInterface, base.InspectInterface):
    """Inspect an NX-OS switch over NX-API using only ``show`` commands.

    Records the NX-OS version and the switch MAC
    (``properties['chassis_mac']``), creates a baremetal port for each
    physical Ethernet interface carrying that interface's burned-in MAC, and
    stores inspection data (see :func:`_inspection_data`), whose
    ``system_vendor`` holds the make, model and serial number as redfish
    inspection does.

    A server's LLDP chassis ID matches a port's MAC when the switch sends
    per-interface chassis IDs (the NX-OS default), or ``chassis_mac`` when it
    is configured with ``lldp chassis-id switch``; which one the switch does is
    ``lldp_chassis_id`` in the plugin data. The LLDP port ID matches the
    interface in the port name either way.

    The switch configuration is never changed and no Ironic port is deleted.
    """

    # A switch has no memory_mb/local_gb/cpu_arch to report.
    ESSENTIAL_PROPERTIES: ClassVar[set] = set()

    def inspect_hardware(self, task):
        node = task.node
        address = node.driver_info["nxos_address"]
        try:
            with cisco_nxos_base.client(node) as client:
                version, iface_body, vdc_body = client.show_many(
                    ["show version", "show interface", "show vdc detail"]
                )
                version = _required(version)
                interfaces = nxos_api.parse_ethernet_interfaces(_required(iface_body))
                chassis_mac = _optional(
                    node,
                    lambda: nxos_api.parse_chassis_mac(_required(vdc_body)),
                    "the switch MAC",
                )
                lldp_chassis_id = _optional(
                    node,
                    lambda: nxos_api.parse_lldp_chassis_id(
                        client.show_text("show running-config lldp")
                    ),
                    "the LLDP chassis-id setting",
                )
        except (nxos_api.NxosApiError, requests.RequestException) as e:
            raise exception.HardwareInspectionFailure(
                error=f"NX-OS {address}: {e}"
            ) from e

        if chassis_mac:
            node.properties = {**node.properties, "chassis_mac": chassis_mac}
        _record_firmware(task, version)
        _sync_ports(task, interfaces)
        task.ports = None  # ports changed; make Ironic reload them
        inventory, plugin_data = _inspection_data(
            version, interfaces, chassis_mac, lldp_chassis_id
        )
        inspect_utils.store_inspection_data(node, inventory, plugin_data, task.context)
        node.save()
        return states.MANAGEABLE


def _required(body: dict | nxos_api.NxosApiError) -> dict:
    """Return a command's output from ``show_many``, raising its error."""
    if isinstance(body, nxos_api.NxosApiError):
        raise body
    return body


def _optional(node, read, what: str):
    """Return ``read()``, or None if the switch cannot report it.

    Used for the details only needed for LLDP matching: the per-port MACs
    still let most servers be matched without them, so they do not fail
    inspection. Not reaching the switch at all still does.
    """
    try:
        value = read()
    except nxos_api.NxosApiError as e:
        LOG.warning("[node:%s] Could not read %s: %s", node.uuid, what, e)
        return None
    if value is None:
        LOG.warning("[node:%s] Switch did not report %s", node.uuid, what)
    return value


def _record_firmware(task, version: dict) -> None:
    """Record the NX-OS release; a switch reporting none does not fail inspect."""
    try:
        cisco_nxos_firmware.record_versions(task, version)
    except exception.UnsupportedDriverExtension:
        LOG.warning(
            "[node:%s] show version reported no NX-OS release",
            task.node.uuid,
        )


def _inspection_data(
    version: dict,
    interfaces: list[dict[str, str]],
    chassis_mac: str | None,
    lldp_chassis_id: str | None,
) -> tuple[dict, dict]:
    """Build the inventory and plugin data stored for the node.

    The inventory uses the standard keys (``interfaces``, ``system_vendor``).
    The plugin data holds what is NX-OS specific: the release, the switch MAC
    and ``lldp_chassis_id``, which is ``switch`` (LLDP sends ``chassis_mac``),
    ``interface`` (LLDP sends each interface's MAC) or None if unknown.
    """
    inventory = {
        "interfaces": [
            {"name": i["interface"], "mac_address": i["mac"]} for i in interfaces
        ],
        "system_vendor": system_vendor(version),
    }
    plugin_data = {
        "nxos_version": cisco_nxos_firmware.nxos_version(version),
        "chassis_mac": chassis_mac,
        "lldp_chassis_id": lldp_chassis_id,
    }
    return inventory, plugin_data


def system_vendor(version: dict) -> dict[str, str]:
    """Return the inventory's ``system_vendor`` from ``show version``.

    Shaped like redfish inspection's: ``manufacturer``, ``product_name`` (the
    chassis model) and ``serial_number``, each left out if not reported.
    """
    found = {
        "manufacturer": version.get("manufacturer") or MANUFACTURER,
        "product_name": version.get("chassis_id"),
        "serial_number": version.get("proc_board_id"),
    }
    return {k: str(v) for k, v in found.items() if v}


def port_name(node, interface: str) -> str:
    return f"{node.name or node.uuid}:{interface}"


def _sync_ports(task, interfaces: list[dict[str, str]]) -> None:
    """Create a port for each interface; correct the MAC of ones that exist.

    A port is matched by name (``<node>:<interface>``) first, then by MAC. A
    port matched only by MAC was created by something else and is left alone.
    A port that cannot be created or corrected because its MAC or name is
    already taken elsewhere is logged and skipped. Ports for interfaces that
    were not found are logged, never deleted.
    """
    node = task.node
    by_name = {p.name: p for p in task.ports if p.name}
    by_mac = {p.address.lower(): p for p in task.ports if p.address}
    seen = set()

    for iface in interfaces:
        name = port_name(node, iface["interface"])
        mac = iface["mac"]
        seen.add(name)

        existing = by_name.get(name)
        if existing is not None:
            _correct_mac(node, existing, mac, by_mac)
            continue
        if (other := by_mac.get(mac)) is not None:
            LOG.warning(
                "[node:%s] %s has MAC %s, already on port %s; not creating %s",
                node.uuid,
                iface["interface"],
                mac,
                other.name or other.uuid,
                name,
            )
            continue

        new = port.Port(
            task.context,
            node_id=node.id,
            address=mac,
            name=name,
            pxe_enabled=False,
        )
        try:
            new.create()
        except exception.MACAlreadyExists:
            LOG.warning(
                "[node:%s] Not creating port %s: MAC %s is on another node's port",
                node.uuid,
                name,
                mac,
            )
            continue
        except exception.PortDuplicateName:
            LOG.warning(
                "[node:%s] Not creating port %s (%s): another node has a port "
                "with that name",
                node.uuid,
                name,
                mac,
            )
            continue
        by_mac[mac] = new
        LOG.info("[node:%s] Created port %s (%s)", node.uuid, name, mac)

    prefix = port_name(node, "")
    missing = sorted(n for n in by_name if n.startswith(prefix) and n not in seen)
    if missing:
        LOG.warning(
            "[node:%s] Interfaces no longer reported by the switch; "
            "keeping their ports: %s",
            node.uuid,
            ", ".join(missing),
        )


def _correct_mac(node, existing, mac: str, by_mac: dict) -> None:
    """Set an existing port's MAC to what the switch reports, if it can be.

    ``by_mac`` is kept in step so later interfaces see the change.
    """
    old = (existing.address or "").lower()
    if old == mac:
        return
    holder = by_mac.get(mac)
    if holder is not None and holder is not existing:
        LOG.warning(
            "[node:%s] Not changing port %s MAC %s -> %s: already on port %s",
            node.uuid,
            existing.name,
            existing.address,
            mac,
            holder.name or holder.uuid,
        )
        return
    previous = existing.address
    existing.address = mac
    try:
        existing.save()
    except exception.MACAlreadyExists:
        existing.address = previous
        LOG.warning(
            "[node:%s] Not changing port %s MAC %s -> %s: on another node's port",
            node.uuid,
            existing.name,
            previous,
            mac,
        )
        return
    LOG.info("[node:%s] Port %s MAC %s -> %s", node.uuid, existing.name, previous, mac)
    if by_mac.get(old) is existing:
        del by_mac[old]
    by_mac[mac] = existing
