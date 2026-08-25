import hashlib
import logging

from understack_workflows import netdev_reconciler
from understack_workflows.dcx.client import DcxClient

logger = logging.getLogger(__name__)

# DCX interface_type of the tenant-facing data ports we enroll. The DRACNet
# (iDRAC/management) port is intentionally excluded: it lives on a "bmc"
# category switch and does not belong to the "-network" physical_network.
DATA_INTERFACE_TYPE = "Public"

# Switch-side interface name prefix. DCX only reports a bare port number, but
# our fabric names ports Ethernet1/<n>.
INTERFACE_PREFIX = "Ethernet1"

# DCX reports the bare switch hostname; append this to form the fully-qualified
# name expected for local_link_connection.switch_info.
SWITCH_DOMAIN = "rackspace.net"

# Switch suffixes that are folded into the VLAN group name when a node's data
# switches all share one of them.
MULTI_LEAF_SUFFIXES = frozenset({"2", "3", "4", "5", "6"})


def deterministic_mac(*parts: object) -> str:
    """Return a stable locally-administered unicast MAC for the given parts.

    We have no real NIC MACs for these appliances, so we synthesise one from
    stable identity (device number + switch + port). Being deterministic keeps
    re-runs idempotent: the reconciler matches ports by name and would rewrite
    the address on every run if we used a random value.
    """
    digest = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    octets = bytearray(digest[:6])
    # Clear the multicast bit and set the locally-administered bit so the
    # address is a valid, unmistakably-synthetic unicast MAC.
    octets[0] = (octets[0] & 0xFE) | 0x02
    return ":".join(f"{octet:02x}" for octet in octets)


def parse_switch_name(switch_name: str) -> tuple[str, str]:
    """Split a switch hostname into ``(rack, suffix)``.

    ``f8-41-2.iad3`` -> ``("f8-41", "2")``.
    """
    short_name = switch_name.split(".")[0]
    rack, _, suffix = short_name.rpartition("-")
    if not rack or not suffix:
        raise ValueError(
            f"Unexpected switch name {switch_name!r}; expected "
            "<rack>-<suffix>.<data_center>"
        )
    return rack, suffix


def rack_of(switch_name: str) -> str:
    """Derive the rack name from a switch hostname: ``f8-41-2.iad3`` -> ``f8-41``."""
    return parse_switch_name(switch_name)[0]


def derive_physnet(switch_names: list[str]) -> str:
    """Derive the physical_network (VLAN group) name from the data switches.

    Reimplemented locally to avoid pulling in the ironic-understack package and
    its oslo.config; it must stay in sync with that package's VLAN group naming
    convention.
    """
    parsed = [parse_switch_name(name) for name in switch_names]
    racks = {rack for rack, _ in parsed}
    suffixes = {suffix for _, suffix in parsed}
    if len(suffixes) == 1 and suffixes <= MULTI_LEAF_SUFFIXES:
        (suffix,) = suffixes
        racks = {f"{rack}-{suffix}" for rack in racks}
    return "/".join(sorted(racks)) + "-network"


def _data_ports(switch_ports: list[dict]) -> list[dict]:
    """Return the inner switch_port dicts for the data (Public) ports, sorted."""
    ports = [
        entry["switch_port"]
        for entry in switch_ports
        if entry.get("switch_port", {}).get("interface_type") == DATA_INTERFACE_TYPE
    ]
    return sorted(ports, key=lambda sp: sp["switch_name"])


def build_enroll_kwargs(
    *,
    device_number: int | str,
    switch_ports: list[dict],
    location: dict,
    name_prefix: str,
    physical_network: str | None = None,
    resource_class: str | None = None,
) -> dict:
    """Transform raw DCX data into keyword args for ``netdev_reconciler.enroll``.

    ``resource_class`` defaults to the lowercased ``name_prefix`` (e.g.
    ``Appliance`` -> ``appliance``). ``physical_network`` is derived from the data
    switches unless explicitly supplied.
    """
    data_ports = _data_ports(switch_ports)
    if not data_ports:
        raise ValueError(
            f"Device {device_number} has no {DATA_INTERFACE_TYPE} switch ports"
        )

    ports = []
    for switch_port in data_ports:
        switch_name = switch_port["switch_name"]
        port_number = switch_port["port_number"]
        ports.append(
            {
                # DCX's port name (e.g. fa0/1) is the device-side interface and
                # is a stable, unique per-port identity. It becomes the Ironic
                # port name node_name:label (e.g. Appliance-1383170:fa0/1).
                "label": switch_port["name"],
                "mac": deterministic_mac(device_number, switch_name, port_number),
                # local_link_connection.switch_info must be the fully-qualified
                # switch name for undersync to match it in Nautobot.
                "switch": f"{switch_name}.{SWITCH_DOMAIN}",
                "intf": f"{INTERFACE_PREFIX}/{port_number}",
            }
        )

    physnet = physical_network or derive_physnet([p["switch"] for p in ports])

    # A DCX device number is an integer; the CLI hands it to us as a string, so
    # coerce it for external_cmdb_id (the node name keeps the string form).
    external_cmdb_id = int(device_number)

    return {
        "name": f"{name_prefix}-{device_number}",
        "physical_network": physnet,
        "ports": ports,
        "external_cmdb_id": external_cmdb_id,
        "resource_class": resource_class or name_prefix.lower(),
        "extra": {
            "external_cmdb_id": external_cmdb_id,
            "rack": location["container"],
            # DCX reports starting_space as a float (e.g. 19.0); a rack unit is
            # a whole number, so store it as an int.
            "position": int(float(location["starting_space"])),
        },
    }


def enroll_from_dcx(
    *,
    client: DcxClient,
    device_number: int | str,
    name_prefix: str,
    physical_network: str | None = None,
    resource_class: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Fetch a device from DCX and enroll it as a netdev Ironic node.

    Returns the computed enroll kwargs (useful for dry-run/logging). When
    ``dry_run`` is set the Ironic API is not touched.
    """
    kwargs = build_enroll_kwargs(
        device_number=device_number,
        switch_ports=client.switch_ports(device_number),
        location=client.location(device_number),
        name_prefix=name_prefix,
        physical_network=physical_network,
        resource_class=resource_class,
    )

    if dry_run:
        logger.info("[dry-run] Would enroll device %s: %s", device_number, kwargs)
        return kwargs

    netdev_reconciler.enroll(**kwargs)
    return kwargs
