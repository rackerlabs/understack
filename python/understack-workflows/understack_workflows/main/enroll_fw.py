import argparse
import logging
import os
from pathlib import Path

from ironicclient.common.apiclient import exceptions as ironic_exceptions

from understack_workflows import firewall
from understack_workflows import helpers
from understack_workflows import ironic_node
from understack_workflows import netdev_reconciler
from understack_workflows.ironic.client import IronicClient

logger = logging.getLogger(__name__)

DEFAULT_FIREWALL_DRIVER = "panos"

# States the HA mate may be in when its pair is promoted. An active mate is
# carrying a router, so promotion only updates its metadata.
MATE_STATES = ("manageable", "available", "active")


def main() -> None:
    """Enroll a firewall, or update its metadata in place.

    Uses the Palo Alto hardware type by default, with management access in
    the node's driver_info and the mate serial in extra.

    """
    helpers.setup_logger()
    args = argument_parser().parse_args()

    node_uuid = enroll_fw(
        name=args.name,
        physical_network=args.physical_network,
        resource_class=args.resource_class,
        driver=args.driver,
        external_cmdb_id=args.external_cmdb_id,
        management_ip=args.management_ip,
        management_switch=args.management_switch,
        management_switch_port=args.management_switch_port,
        mate_serial=args.mate_serial,
        ha_role=args.ha_role,
        serial=args.serial,
        vendor=args.vendor,
        model=args.model,
    )

    if args.node_uuid_output:
        Path(args.node_uuid_output).write_text(node_uuid + "\n")


def _strip(value: str | None) -> str:
    """Return value without surrounding whitespace ("" for None)."""
    return (value or "").strip()


def _require(value: str | None, message: str) -> str:
    """Return value stripped, or raise ValueError(message) if it is blank."""
    value = _strip(value)
    if not value:
        raise ValueError(message)
    return value


def _require_specific_resource_class(resource_class: str | None) -> str:
    """Return a normalized, purpose-made resource class.

    argparse(required=True) only requires the flag to be present, and the engine
    turns an empty value into the generic default.
    """
    normalized = _strip(resource_class)
    if not normalized or normalized.lower() == netdev_reconciler.DEFAULT_RESOURCE_CLASS:
        raise ValueError(
            "enroll-fw requires an explicit, purpose-made --resource-class; "
            f"got {resource_class!r}. The generic default is not allowed."
        )
    return normalized


def _require_management_location(
    management_switch: str, management_switch_port: str
) -> tuple[str, str]:
    """Return (switch, port) after checking both are non-empty."""
    switch = _strip(management_switch)
    port = _strip(management_switch_port)
    missing = []
    if not switch:
        missing.append("--management-switch")
    if not port:
        missing.append("--management-switch-port")
    if missing:
        raise ValueError(
            f"enroll-fw requires {' and '.join(missing)}: the management switch "
            "and port cannot be blank."
        )
    return switch, port


def enroll_fw(
    *,
    name: str,
    physical_network: str,
    resource_class: str,
    driver: str = DEFAULT_FIREWALL_DRIVER,
    external_cmdb_id: int | str | None = None,
    management_ip: str = "",
    management_switch: str = "",
    management_switch_port: str = "",
    mate_serial: str = "",
    ha_role: str = "",
    serial: str = "",
    vendor: str = "",
    model: str = "",
) -> str:
    """Enroll a firewall, or update an in-service one in place; return its UUID.

    Inspection finds the ports over LLDP and labels them; enroll never takes a
    ports list, because a typed list that disagrees with the cabling would
    configure switch ports that don't belong to this firewall.
    """
    driver = _require(driver, "enroll-fw requires a non-empty --driver")
    physical_network = _require(
        physical_network, "enroll-fw requires --physical-network"
    )
    if ha_role:
        _require(mate_serial, "enroll-fw requires --mate-serial with --ha-role")
    resource_class = _require_specific_resource_class(resource_class)
    management_switch, management_switch_port = _require_management_location(
        management_switch, management_switch_port
    )
    driver_info, extra, properties = firewall.firewall_metadata(
        management_ip=management_ip,
        management_switch=management_switch,
        management_switch_port=management_switch_port,
        mate_serial=mate_serial,
        serial=serial,
        vendor=vendor,
        model=model,
    )
    if external_cmdb_id not in (None, ""):
        extra = {**extra, "external_cmdb_id": external_cmdb_id}
    # What every path below writes on the node.
    node_fields = {
        "resource_class": resource_class,
        "driver": driver,
        "driver_info": driver_info,
        "extra": extra,
        "properties": properties,
        "traits": firewall.ha_role_traits(ha_role),
    }

    # Look up the node first so we can tell an in-service (active) firewall from
    # one we may (re)enroll. Only the active case is special-cased here; every
    # other state is handled by the shared engine (which rejects the states it
    # cannot enroll).
    client = IronicClient()
    node = _get_node_or_none(client, name)

    if node is not None and getattr(node, "provision_state", None) == "active":
        _update_active_firewall(
            client=client,
            node=node,
            name=name,
            **node_fields,
        )
        return node.uuid

    node_uuid = _make_manageable(client=client, name=name, **node_fields)
    _inspect_and_provide(client, node_uuid, physical_network, ha_role)
    return node_uuid


def _get_node_or_none(client: IronicClient, name: str):
    """Return the node named ``name``, or None if it does not exist yet."""
    try:
        return client.get_node(name)
    except ironic_exceptions.NotFound:
        return None


def _make_manageable(
    *,
    client: IronicClient,
    name: str,
    resource_class: str,
    driver: str,
    driver_info: dict,
    extra: dict,
    properties: dict,
    traits: dict[str, bool],
) -> str:
    """Create or update the firewall's node, and make it manageable.

    Inspection then finds the ports and labels them.
    """
    node, created = netdev_reconciler.find_or_create_netdev_node(
        client=client,
        name=name,
        resource_class=resource_class,
        driver=driver,
        driver_info=driver_info,
        extra=extra,
        properties=properties,
    )
    netdev_reconciler.make_manageable(node, node.provision_state)
    if not created:
        netdev_reconciler.update_node_metadata(
            client=client,
            node=node,
            resource_class=resource_class,
            driver_info=driver_info,
            extra=extra,
            properties=properties,
        )
    netdev_reconciler.update_node_traits(client=client, node=node, traits=traits)
    return node.uuid


def _inspect_and_provide(
    client: IronicClient,
    node_uuid: str,
    physical_network: str,
    ha_role: str = "",
) -> None:
    """Inspect the firewall, check its outside and inside ports, then provide it.

    Each role needs exactly one port. Those ports get the given
    physical_network. A failed check leaves the node manageable.

    A unit of an HA pair is provided only once inspection confirms the pair
    (extra.ha_operational); then both units are linked and provided together.
    """
    node = client.get_node(node_uuid)
    logger.info("[node:%s] Inspecting to discover and check the ports", node.uuid)
    ironic_node.transition(node, target_state="inspect", expected_state="manageable")
    role_ports = _checked_role_ports(client, node)
    _set_physical_network(client, node, role_ports.values(), physical_network)

    if not ha_role:
        _provide(node)
        return

    # Inspection wrote extra.ha_operational, so read the node again.
    node = client.get_node(node.uuid)
    if _extra(node).get("ha_operational") is not True:
        logger.warning(
            "[node:%s] Left manageable: HA pair not confirmed yet. It is waiting "
            "for its mate, or the HA checks failed; see the conductor log",
            node.uuid,
        )
        return
    _promote_ha_pair(client, node, ha_role, physical_network, role_ports)


def _checked_role_ports(client: IronicClient, node) -> dict:
    """Return the outside and inside port inspection left, as {role: port}.

    Each role needs exactly one port.
    """
    role_ports = {}
    for role, found in _ports_by_role(client.list_ports(node.uuid)).items():
        if len(found) != 1:
            raise _left_manageable(
                node, f"Inspection left {len(found)} {role} ports, expected one"
            )
        role_ports[role] = found[0]
    return role_ports


def _set_physical_network(
    client: IronicClient, node, ports, physical_network: str
) -> None:
    """Give each port the physical_network, where it differs."""
    for port in ports:
        if port.physical_network != physical_network:
            logger.info(
                "[node:%s] Setting physical_network=%s on port %s (was %s)",
                node.uuid,
                physical_network,
                port.name,
                port.physical_network,
            )
            client.update_port(port.uuid, [_add("/physical_network", physical_network)])


def _promote_ha_pair(
    client: IronicClient, node, ha_role: str, physical_network: str, role_ports
) -> None:
    """Link a confirmed HA pair, and provide both units.

    This node's inspection checked both boxes, so the mate's ha_operational
    is set from here. Every check runs before the first write, so a failed
    check leaves both units as they were. The mate is provided first. An
    active mate (carrying a router) only gets its metadata updated.
    """
    mate = _find_mate(client, node)
    if ha_role == "primary":
        primary, secondary, mate_role = node, mate, "secondary"
    else:
        primary, secondary, mate_role = mate, node, "primary"

    problems = [
        *_unit_problems(client, node, mate, mate_role),
        *_port_problems(client, mate, physical_network, role_ports),
        *_link_problems(client, primary, secondary),
    ]
    if problems:
        raise RuntimeError(
            f"[node:{node.uuid}] HA pair {_extra(node)['serial']} / "
            f"{_extra(node)['mate_serial']} not promoted; both units stay as "
            "they are: " + "; ".join(problems)
        )

    _link(client, primary, secondary)
    if _extra(mate).get("ha_operational") is not True:
        logger.info("[node:%s] Setting its mate's ha_operational", mate.uuid)
        client.update_node(mate.uuid, [_add("/extra/ha_operational", True)])
    if mate.provision_state == "manageable":
        _provide(mate)
    _provide(node)


def _find_mate(client: IronicClient, node):
    """Return the one node whose extra.serial is this node's mate_serial."""
    if not _extra(node).get("serial"):
        raise _left_manageable(
            node,
            "Has no extra.serial, so the HA pair can't be checked; re-run "
            "with --serial",
        )
    mate_serial = _extra(node).get("mate_serial")
    # Children too: once linked, the secondary is a child node.
    matches = [
        candidate
        for candidate in client.list_nodes(
            driver=node.driver, detail=True, include_children=True
        )
        if _extra(candidate).get("serial") == mate_serial
    ]
    if len(matches) != 1 or matches[0].uuid == node.uuid:
        raise _left_manageable(
            node,
            f"Found {len(matches)} {node.driver} nodes with serial {mate_serial} "
            "(its mate_serial), expected one other node",
        )
    return matches[0]


def _unit_problems(client: IronicClient, node, mate, mate_role: str) -> list[str]:
    """Return why the two units can't be one HA pair: identity, role, pool, state."""
    problems = []
    serial = _extra(node)["serial"]
    mates_mate = _extra(mate).get("mate_serial")
    if mates_mate != serial:
        problems.append(f"the mate's mate_serial is {mates_mate!r}, not {serial!r}")
    expected = firewall.HA_ROLE_TRAITS[mate_role]
    mate_roles = set(client.get_node_traits(mate.uuid)) & set(
        firewall.HA_ROLE_TRAITS.values()
    )
    if mate_roles != {expected}:
        problems.append(
            f"the mate's HA traits are {sorted(mate_roles)}, expected {expected} only"
        )
    for field in ("resource_class", "owner"):
        mine, theirs = getattr(node, field, None), getattr(mate, field, None)
        if mine != theirs:
            problems.append(f"{field} is {mine!r} here but {theirs!r} on the mate")
    for unit, label in ((node, "this node"), (mate, "the mate")):
        if getattr(unit, "maintenance", False):
            problems.append(f"{label} is in maintenance")
    if mate.provision_state not in MATE_STATES:
        problems.append(
            f"the mate is {mate.provision_state}; re-run when its inspection or "
            "enrollment finishes"
        )
    return problems


def _port_problems(
    client: IronicClient, mate, physical_network: str, role_ports: dict
) -> list[str]:
    """Return how the mate's outside/inside ports differ from this node's."""
    problems = []
    for role, found in _ports_by_role(client.list_ports(mate.uuid)).items():
        if len(found) != 1:
            problems.append(f"the mate has {len(found)} {role} ports, expected one")
            continue
        if found[0].physical_network != physical_network:
            problems.append(
                f"the mate's {role} port is on {found[0].physical_network!r}, "
                f"not {physical_network!r}"
            )
        mine = _extra(role_ports[role]).get("bios_name")
        theirs = _extra(found[0]).get("bios_name")
        if not mine or mine != theirs:
            # PAN-OS config sync copies interface names to the other box.
            problems.append(f"{role} is {mine!r} here but {theirs!r} on the mate")
    return problems


def _link_problems(client: IronicClient, primary, secondary) -> list[str]:
    """Return the links left from an earlier pairing; those are fixed by hand.

    The one exception: a secondary whose old primary node was deleted (the
    end of a box replacement). _link points it at the new primary.
    """
    problems = []
    if getattr(primary, "parent_node", None):
        problems.append(
            f"the primary is itself linked to {primary.parent_node}; "
            "unset its parent_node"
        )
    others = [
        child.uuid
        for child in client.list_child_nodes(primary.uuid)
        if child.uuid != secondary.uuid
    ]
    if others:
        problems.append(
            f"the primary already has another secondary {others}; "
            "delete it or unset its parent_node"
        )
    linked = getattr(secondary, "parent_node", None)
    if (
        linked
        and linked != primary.uuid
        and _get_node_or_none(client, linked) is not None
    ):
        problems.append(
            f"the secondary is linked to another primary {linked}; "
            "unset its parent_node"
        )
    return problems


def _link(client: IronicClient, primary, secondary) -> None:
    """Make the secondary a child of the primary, with power coupling off.

    Ironic powers a child's parent on and off with it, unless the child has
    driver_info.has_dedicated_power_supply. Each firewall has its own power.
    One update sets both, so the link never exists without the flag.
    """
    old_parent = getattr(secondary, "parent_node", None)
    ops = []
    if old_parent != primary.uuid:
        ops.append(_add("/parent_node", primary.uuid))
    driver_info = getattr(secondary, "driver_info", None) or {}
    if driver_info.get("has_dedicated_power_supply") is not True:
        ops.append(_add("/driver_info/has_dedicated_power_supply", True))
    if ops:
        logger.info(
            "[node:%s] Linking it to its primary %s (was %s)",
            secondary.uuid,
            primary.uuid,
            old_parent,
        )
        client.update_node(secondary.uuid, ops)


def _ports_by_role(ports) -> dict[str, list]:
    """Group ports by router role: {"outside": [...], "inside": [...]}."""
    ports = list(ports)
    return {
        role: [port for port in ports if getattr(port, "category", None) == role]
        for role in firewall.PORT_ROLES
    }


def _extra(obj) -> dict:
    """Return a node's or port's extra, or {} if it has none."""
    return getattr(obj, "extra", None) or {}


def _left_manageable(node, reason: str) -> RuntimeError:
    """Return the error for a check that stops this run before provide."""
    return RuntimeError(f"[node:{node.uuid}] {reason}; leaving it manageable")


def _add(path: str, value) -> dict:
    """Return a JSON patch "add" op that keeps the value's type.

    args_array_to_patch would turn True into the string "True".
    """
    return {"op": "add", "path": path, "value": value}


def _provide(node) -> None:
    """Make a manageable node available."""
    ironic_node.transition(node, target_state="provide", expected_state="available")


def _update_active_firewall(
    *,
    client: IronicClient,
    node,
    name: str,
    resource_class: str,
    driver: str,
    driver_info: dict,
    extra: dict,
    properties: dict,
    traits: dict[str, bool],
) -> None:
    """Update firewall metadata on an in-service (active) node, in place.

    An active firewall is carrying live traffic, so its base configuration must
    not change here: its ports are left alone, and a different driver,
    resource class or HA role is refused. Only driver_info/extra/properties
    are patched.
    """
    _reject_identity_drift(
        client=client,
        node=node,
        name=name,
        driver=driver,
        resource_class=resource_class,
        traits=traits,
    )

    logger.info(
        "[node:%s] Node is active; updating firewall metadata only",
        node.uuid,
    )
    firewall.apply_node_metadata(client, node, driver_info, extra, properties)


def _reject_identity_drift(
    *,
    client: IronicClient,
    node,
    name: str,
    driver: str,
    resource_class: str,
    traits: dict[str, bool],
) -> None:
    """Refuse to change an active node's driver, resource class or HA role."""
    node_driver = getattr(node, "driver", None)
    if node_driver != driver:
        raise RuntimeError(
            f"Node {name} ({node.uuid}) is active with driver {node_driver!r}; "
            f"refusing to enroll it as {driver!r}"
        )

    current_roles = set(client.get_node_traits(node.uuid)) & set(traits)
    wanted_roles = {trait for trait, on in traits.items() if on}
    for field, current, wanted in (
        ("resource_class", getattr(node, "resource_class", None), resource_class),
        ("HA traits", sorted(current_roles), sorted(wanted_roles)),
    ):
        if current != wanted:
            raise RuntimeError(
                f"[node:{node.uuid}] Node is active with {field} {current!r}; "
                f"refusing to change it to {wanted!r} on an in-service firewall"
            )


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Enroll a firewall (defaults to the panos hardware type)",
    )
    parser.add_argument(
        "--node-uuid-output",
        help="Write node UUID to this file after successful enrollment",
    )
    parser.add_argument("--name", required=True, help="Ironic node name")
    parser.add_argument(
        "--physical-network",
        required=True,
        help="Port physical_network, the VLAN group in Nautobot (e.g. f20-3-network)",
    )
    parser.add_argument(
        "--resource-class",
        required=True,
        help="Ironic resource class (required: use a purpose-made pool, not "
        "the generic default, or the router flavor may adopt wrong hardware)",
    )
    parser.add_argument(
        "--driver",
        default=DEFAULT_FIREWALL_DRIVER,
        help=(
            "Ironic hardware type to enroll the node as "
            f"(default: {DEFAULT_FIREWALL_DRIVER}). Must match an existing "
            "node's driver."
        ),
    )
    parser.add_argument(
        "--external-cmdb-id",
        type=helpers.int_or_str,
        default="",
        help="CMDB ID",
    )
    parser.add_argument(
        "--management-ip",
        default="",
        help="Management IP -> driver_info.management_ip",
    )
    parser.add_argument(
        "--management-switch",
        required=True,
        help="Management switch name -> driver_info.management_switch",
    )
    parser.add_argument(
        "--management-switch-port",
        required=True,
        help="Management switch port -> driver_info.management_switch_port",
    )
    parser.add_argument(
        "--mate-serial",
        default="",
        help="HA mate serial number -> extra.mate_serial",
    )
    parser.add_argument(
        "--ha-role",
        choices=["", *firewall.HA_ROLE_TRAITS],
        default="",
        help="HA role, set as node trait CUSTOM_PRIMARY or CUSTOM_SECONDARY "
        "(needs --mate-serial). Routers never get a secondary.",
    )
    parser.add_argument(
        "--serial",
        default="",
        help="Device's own serial number -> extra.serial (Nautobot sync)",
    )
    parser.add_argument(
        "--vendor",
        default="Palo Alto",
        help="Device vendor -> properties.vendor (Nautobot sync)",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Device model, e.g. PA-1410 -> properties.model (Nautobot sync)",
    )
    return parser


if __name__ == "__main__":
    main()
