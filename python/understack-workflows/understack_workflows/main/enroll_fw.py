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
        ports=netdev_reconciler.parse_ports_arg(args.ports),
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


def _require_specific_resource_class(resource_class: str | None) -> str:
    """Return a normalized, purpose-made resource class.

    argparse(required=True) only requires the flag to be present, and the engine
    turns an empty value into the generic default.
    """
    normalized = (resource_class or "").strip()
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
    switch = (management_switch or "").strip()
    port = (management_switch_port or "").strip()
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
    ports: list[dict],
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
    driver = (driver or "").strip()
    if not driver:
        raise ValueError("enroll-fw requires a non-empty --driver")
    if not (physical_network or "").strip():
        raise ValueError("enroll-fw requires --physical-network")
    if ha_role and not (mate_serial or "").strip():
        raise ValueError("enroll-fw requires --mate-serial with --ha-role")
    traits = firewall.ha_role_traits(ha_role)
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
            physical_network=physical_network,
            ports=ports,
            resource_class=resource_class,
            driver=driver,
            driver_info=driver_info,
            extra=extra,
            properties=properties,
            traits=traits,
        )
        return node.uuid

    if ports:
        # The engine writes the metadata, ports and roles but leaves the node
        # manageable, so a router can't adopt it before inspection checks it.
        node_uuid = netdev_reconciler.enroll(
            name=name,
            physical_network=physical_network,
            ports=ports,
            resource_class=resource_class,
            driver=driver,
            driver_info=driver_info,
            extra=extra,
            properties=properties,
            assign_roles=True,
            traits=traits,
            provide=False,
        )
    else:
        node_uuid = _make_manageable_without_ports(
            client=client,
            name=name,
            resource_class=resource_class,
            driver=driver,
            driver_info=driver_info,
            extra=extra,
            properties=properties,
            traits=traits,
        )

    _inspect_and_provide(client, node_uuid, physical_network, ports)
    return node_uuid


def _get_node_or_none(client: IronicClient, name: str):
    """Return the node named ``name``, or None if it does not exist yet."""
    try:
        return client.get_node(name)
    except ironic_exceptions.NotFound:
        return None


def _make_manageable_without_ports(
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
    """Create or update a firewall that has no ports yet, and make it manageable.

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


def _role_macs(ports: list[dict]) -> dict[str, str]:
    """Return the MAC that enroll gives each router role."""
    labelled = netdev_reconciler.assign_port_roles(
        netdev_reconciler.build_netdev_ports(ports)
    )
    return {
        port.category: port.mac.lower()
        for port in labelled
        if port.category in netdev_reconciler.PORT_ROLES
    }


def _inspect_and_provide(
    client: IronicClient, node_uuid: str, physical_network: str, ports: list[dict]
) -> None:
    """Inspect the firewall, check its outside and inside ports, then provide it.

    Each role needs exactly one port, and with ports given, on the MAC enroll
    gave it. Those ports get the given physical_network. A failed check leaves
    the node manageable.
    """
    node = client.get_node(node_uuid)
    given_roles = _role_macs(ports) if ports else None
    logger.info("[node:%s] Inspecting to discover and check the ports", node.uuid)
    ironic_node.transition(node, target_state="inspect", expected_state="manageable")

    node_ports = list(client.list_ports(node.uuid))
    role_ports = []
    for role in netdev_reconciler.PORT_ROLES:
        found = [p for p in node_ports if getattr(p, "category", None) == role]
        if len(found) != 1:
            raise RuntimeError(
                f"[node:{node.uuid}] Inspection left {len(found)} {role} ports, "
                "expected one; leaving it manageable"
            )
        mac = (found[0].address or "").lower()
        if given_roles is not None and mac != given_roles[role]:
            raise RuntimeError(
                f"[node:{node.uuid}] Inspection put {role} on {mac}, but the ports "
                f"list gave it to {given_roles[role]}; check the cabling or the "
                "ports list. Leaving it manageable"
            )
        role_ports.append(found[0])

    for port in role_ports:
        if port.physical_network != physical_network:
            logger.info(
                "[node:%s] Setting physical_network=%s on port %s (was %s)",
                node.uuid,
                physical_network,
                port.name,
                port.physical_network,
            )
            client.update_port(
                port.uuid,
                [
                    {
                        "op": "add",
                        "path": "/physical_network",
                        "value": physical_network,
                    }
                ],
            )

    ironic_node.transition(node, target_state="provide", expected_state="available")


def _update_active_firewall(
    *,
    client: IronicClient,
    node,
    name: str,
    physical_network: str,
    ports: list[dict],
    resource_class: str,
    driver: str,
    driver_info: dict,
    extra: dict,
    properties: dict,
    traits: dict[str, bool],
) -> None:
    """Update firewall metadata on an in-service (active) node, in place.

    An active firewall is carrying live traffic, so its base configuration must
    not change here. We re-validate the submitted ports and compare them
    read-only against the node's real ports.
    If everything matches we patch only driver_info/extra/properties.
    """
    node_driver = getattr(node, "driver", None)
    if node_driver != driver:
        raise RuntimeError(
            f"Node {name} ({node.uuid}) is active with driver {node_driver!r}; "
            f"refusing to enroll it as {driver!r}"
        )

    node_resource_class = getattr(node, "resource_class", None)
    if node_resource_class != resource_class:
        raise RuntimeError(
            f"[node:{node.uuid}] Node is active with resource_class "
            f"{node_resource_class!r}; refusing to change it to "
            f"{resource_class!r} on an in-service firewall"
        )

    current = set(client.get_node_traits(node.uuid)) & set(traits)
    wanted = {trait for trait, on in traits.items() if on}
    if current != wanted:
        raise RuntimeError(
            f"[node:{node.uuid}] Node is active with HA traits {sorted(current)}; "
            f"refusing to change them to {sorted(wanted)} on an in-service firewall"
        )

    # Without ports there is nothing to compare: inspection owns them.
    if ports:
        _reject_structural_drift(
            client=client,
            node=node,
            name=name,
            physical_network=physical_network,
            netdev_ports=netdev_reconciler.build_netdev_ports(ports),
        )

    logger.info(
        "[node:%s] Node is active; ports/physical_network match the request, "
        "updating firewall metadata only",
        node.uuid,
    )
    firewall.apply_node_metadata(client, node, driver_info, extra, properties)


def _reject_structural_drift(
    *,
    client: IronicClient,
    node,
    name: str,
    physical_network: str,
    netdev_ports: list,
) -> None:
    """Refuse if any requested port would create/update on the node.

    Reuses the engine's read-only port planner: a non-None plan means the port
    is missing or differs (MAC, switch, interface, physical_network, ...).
    """
    node_ports = list(client.list_ports(node.uuid))
    ports_by_mac = {(p.address or "").lower(): p for p in node_ports}
    ports_by_name = {p.name: p for p in node_ports if p.name}

    for port in netdev_ports:
        plan = netdev_reconciler.plan_netdev_port(
            node=node,
            node_name=name,
            physical_network=physical_network,
            port=port,
            existing=ports_by_name.get(f"{name}:{port.label}"),
            ports_by_mac=ports_by_mac,
            # This path assigns no roles, so a live firewall's outside/inside
            # labels must not count as drift.
            manage_category=False,
        )
        if plan is not None:
            raise RuntimeError(
                f"[node:{node.uuid}] Node is active; refusing to change ports/"
                f"physical_network on an in-service firewall (port "
                f"{name}:{port.label} would be {plan['kind']}d). Reconcile the "
                "base configuration through a maintenance window, not a metadata "
                "update."
            )

    netdev_reconciler.warn_orphan_ports(node, name, node_ports, netdev_ports)


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
        "--ports",
        default="[]",
        help="JSON array of ports (same format as enroll-netdev). 'switch' must "
        "be the switch FQDN (e.g. n11-22-1.dfw3.rackspace.net) so the Nautobot "
        "sync can resolve the cable. Optional per-port 'bios_name' (the device "
        "interface name); defaults to the label. At least two ports: the "
        "lowest-numbered interface becomes the router's outside NIC (gateway) "
        "and the next one its inside NIC (subnets). The firewall is inspected "
        "either way, and inspection must keep those roles on these ports. Leave "
        "it out to have inspection discover the ports over LLDP and label them.",
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
        required=False,
        default="",
        help="CMDB ID",
    )
    parser.add_argument(
        "--management-ip",
        required=False,
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
        required=False,
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
        required=False,
        default="",
        help="Device's own serial number -> extra.serial (Nautobot sync)",
    )
    parser.add_argument(
        "--vendor",
        required=False,
        default="Palo Alto",
        help="Device vendor -> properties.vendor (Nautobot sync)",
    )
    parser.add_argument(
        "--model",
        required=False,
        default="",
        help="Device model, e.g. PA-1410 -> properties.model (Nautobot sync)",
    )
    return parser


if __name__ == "__main__":
    main()
