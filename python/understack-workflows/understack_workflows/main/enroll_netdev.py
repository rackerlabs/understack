import argparse
import logging
import os
from dataclasses import dataclass

from ironicclient.v1.node import Node

from understack_workflows import helpers
from understack_workflows import ironic_node
from understack_workflows.ironic.client import IronicClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NetdevPort:
    label: str
    mac: str
    switch: str
    interface: str


def main() -> None:
    """Create a netdev baremetal node, its 2 ports, and make it available."""
    helpers.setup_logger()
    args = argument_parser().parse_args()

    enroll(
        name=args.name,
        physical_network=args.physical_network,
        port1_mac=args.port1_mac,
        port1_switch=args.port1_switch,
        port1_intf=args.port1_intf,
        port2_mac=args.port2_mac,
        port2_switch=args.port2_switch,
        port2_intf=args.port2_intf,
        external_cmdb_id=args.external_cmdb_id,
        resource_class=args.resource_class,
    )


def enroll(
    *,
    name: str,
    physical_network: str,
    port1_mac: str,
    port1_switch: str,
    port1_intf: str,
    port2_mac: str,
    port2_switch: str,
    port2_intf: str,
    external_cmdb_id: int | str | None = None,
    resource_class: str | None = "generic",
) -> None:
    effective_resource_class = resource_class or "generic"
    logger.info(
        "Starting enroll-netdev workflow name=%s physical_network=%s "
        "resource_class=%s",
        name,
        physical_network,
        effective_resource_class,
    )

    if external_cmdb_id:
        logger.info(
            "Recording external_cmdb_id=%s on the Ironic node",
            external_cmdb_id,
        )
    else:
        logger.info("No external_cmdb_id provided")

    client = IronicClient()
    node = create_netdev_node(
        client=client,
        name=name,
        resource_class=effective_resource_class,
        external_cmdb_id=external_cmdb_id,
    )

    ports = [
        NetdevPort("port1", port1_mac, port1_switch, port1_intf),
        NetdevPort("port2", port2_mac, port2_switch, port2_intf),
    ]
    for port in ports:
        create_netdev_port(
            client=client,
            node=node,
            node_name=name,
            physical_network=physical_network,
            port=port,
        )

    logger.info(
        "[node:%s] Requesting manage transition, expecting manageable",
        node.uuid,
    )
    ironic_node.transition(node, target_state="manage", expected_state="manageable")
    logger.info("[node:%s] Node is manageable", node.uuid)

    logger.info(
        "[node:%s] Requesting provide transition, expecting available",
        node.uuid,
    )
    ironic_node.transition(node, target_state="provide", expected_state="available")
    logger.info("[node:%s] Node is available", node.uuid)
    logger.info(
        "Completed enroll-netdev workflow name=%s node_uuid=%s",
        name,
        node.uuid,
    )


def create_netdev_node(
    *,
    client: IronicClient,
    name: str,
    resource_class: str,
    external_cmdb_id: int | str | None = None,
) -> Node:
    node_data = {
        "automated_clean": False,
        "driver": "netdev",
        "name": name,
        "resource_class": resource_class,
    }
    if external_cmdb_id:
        node_data["extra"] = {"external_cmdb_id": external_cmdb_id}

    logger.info(
        "Creating netdev Ironic node name=%s driver=%s "
        "resource_class=%s automated_clean=%s",
        node_data["name"],
        node_data["driver"],
        node_data["resource_class"],
        node_data["automated_clean"],
    )
    node = client.create_node(node_data)
    logger.info("Created netdev Ironic node name=%s uuid=%s", name, node.uuid)
    return node


def create_netdev_port(
    *,
    client: IronicClient,
    node: Node,
    node_name: str,
    physical_network: str,
    port: NetdevPort,
) -> None:
    port_name = f"{node_name}:{port.label}"
    port_data = {
        "address": port.mac,
        "category": "network",
        "local_link_connection": {
            "switch_id": "00:00:00:00:00:00",
            "switch_info": port.switch,
            "port_id": port.interface,
        },
        "name": port_name,
        "node_uuid": node.uuid,
        "physical_network": physical_network,
    }

    logger.info(
        "[node:%s] Creating baremetal port name=%s mac=%s "
        "physical_network=%s switch_id=%s switch_info=%s port_id=%s "
        "category=network",
        node.uuid,
        port_name,
        port.mac,
        physical_network,
        "00:00:00:00:00:00",
        port.switch,
        port.interface,
    )
    created_port = client.create_port(port_data)
    logger.info(
        "[node:%s] Created baremetal port name=%s uuid=%s",
        node.uuid,
        port_name,
        getattr(created_port, "uuid", ""),
    )


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Run the netdev enroll workflow",
    )
    parser.add_argument("--name", required=True, help="Ironic node name")
    parser.add_argument(
        "--physical-network",
        required=True,
        help="Port physical_network",
    )
    parser.add_argument("--port1-mac", required=True, help="MAC address for port1")
    parser.add_argument("--port1-switch", required=True, help="Switch name for port1")
    parser.add_argument(
        "--port1-intf",
        required=True,
        help="Switch interface name for port1",
    )
    parser.add_argument("--port2-mac", required=True, help="MAC address for port2")
    parser.add_argument("--port2-switch", required=True, help="Switch name for port2")
    parser.add_argument(
        "--port2-intf",
        required=True,
        help="Switch interface name for port2",
    )
    parser.add_argument(
        "--external-cmdb-id",
        type=helpers.int_or_str,
        required=False,
        default="",
        help="CMDB ID",
    )
    parser.add_argument(
        "--resource-class",
        required=False,
        default="generic",
        help="Ironic resource class",
    )
    return parser


if __name__ == "__main__":
    main()
