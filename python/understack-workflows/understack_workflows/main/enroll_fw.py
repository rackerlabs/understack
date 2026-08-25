import argparse
import logging
import os

from ironicclient.common.apiclient import exceptions as ironic_exceptions

from understack_workflows import firewall
from understack_workflows import helpers
from understack_workflows import netdev_reconciler
from understack_workflows.ironic.client import IronicClient

logger = logging.getLogger(__name__)


def main() -> None:
    """Enroll a firewall, or update its metadata in place.

    A firewall is a generic netdev node plus firewall metadata: management
    access in the node's driver_info and the mate serial in extra.

    """
    helpers.setup_logger()
    args = argument_parser().parse_args()

    enroll_fw(
        name=args.name,
        physical_network=args.physical_network,
        ports=netdev_reconciler.parse_ports_arg(args.ports),
        resource_class=args.resource_class,
        external_cmdb_id=args.external_cmdb_id,
        management_ip=args.management_ip,
        management_switch=args.management_switch,
        management_switch_port=args.management_switch_port,
        mate_serial=args.mate_serial,
    )


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
    external_cmdb_id: int | str | None = None,
    management_ip: str = "",
    management_switch: str = "",
    management_switch_port: str = "",
    mate_serial: str = "",
) -> None:
    resource_class = _require_specific_resource_class(resource_class)
    management_switch, management_switch_port = _require_management_location(
        management_switch, management_switch_port
    )
    driver_info, extra = firewall.firewall_metadata(
        management_ip=management_ip,
        management_switch=management_switch,
        management_switch_port=management_switch_port,
        mate_serial=mate_serial,
    )

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
            external_cmdb_id=external_cmdb_id,
            driver_info=driver_info,
            extra=extra,
        )
        return

    # New or re-enrollable node: the engine writes the metadata inside the
    # enrollment lifecycle (at create, or patched before the node becomes
    # available), so the node is never allocatable in an under-described state.
    netdev_reconciler.enroll(
        name=name,
        physical_network=physical_network,
        ports=ports,
        resource_class=resource_class,
        external_cmdb_id=external_cmdb_id,
        driver_info=driver_info,
        extra=extra,
    )


def _get_node_or_none(client: IronicClient, name: str):
    """Return the node named ``name``, or None if it does not exist yet."""
    try:
        return client.get_node(name)
    except ironic_exceptions.NotFound:
        return None


def _update_active_firewall(
    *,
    client: IronicClient,
    node,
    name: str,
    physical_network: str,
    ports: list[dict],
    resource_class: str,
    external_cmdb_id: int | str | None,
    driver_info: dict,
    extra: dict,
) -> None:
    """Update firewall metadata on an in-service (active) node, in place.

    An active firewall is carrying live traffic, so its base configuration must
    not change here. We re-validate the submitted ports and compare them
    read-only against the node's real ports.
    If everything matches we patch only driver_info/extra.
    """
    node_driver = getattr(node, "driver", None)
    if node_driver != "netdev":
        raise RuntimeError(
            f"Node {name} ({node.uuid}) is active with driver {node_driver!r}; "
            "refusing to modify a non-netdev node"
        )

    node_resource_class = getattr(node, "resource_class", None)
    if node_resource_class != resource_class:
        raise RuntimeError(
            f"[node:{node.uuid}] Node is active with resource_class "
            f"{node_resource_class!r}; refusing to change it to "
            f"{resource_class!r} on an in-service firewall"
        )

    netdev_ports = netdev_reconciler.build_netdev_ports(ports)
    _reject_structural_drift(
        client=client,
        node=node,
        name=name,
        physical_network=physical_network,
        netdev_ports=netdev_ports,
    )

    active_extra = dict(extra)
    if external_cmdb_id not in (None, ""):
        active_extra["external_cmdb_id"] = external_cmdb_id

    logger.info(
        "[node:%s] Node is active; ports/physical_network match the request, "
        "updating firewall metadata only",
        node.uuid,
    )
    firewall.apply_node_metadata(client, node, driver_info, active_extra)


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
        description="Enroll a firewall (netdev node + firewall metadata)",
    )
    parser.add_argument("--name", required=True, help="Ironic node name")
    parser.add_argument(
        "--physical-network",
        required=True,
        help="Port physical_network",
    )
    parser.add_argument(
        "--ports",
        required=True,
        help="JSON array of ports (same format as enroll-netdev)",
    )
    parser.add_argument(
        "--resource-class",
        required=True,
        help="Ironic resource class (required: use a purpose-made pool, not "
        "the generic default, or the router flavor may adopt wrong hardware)",
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
    return parser


if __name__ == "__main__":
    main()
