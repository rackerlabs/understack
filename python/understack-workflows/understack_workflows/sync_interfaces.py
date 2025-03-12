from ironicclient.v1.port import Port

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.port_configuration import PortConfiguration
from understack_workflows.bmc_chassis_info import InterfaceInfo
from understack_workflows import data_center

logger = setup_logger(__name__)


def update_ironic_baremetal_ports(
    ironic_node,
    discovered_interfaces: list[InterfaceInfo],
    pxe_interface_name: str,
    ironic_client: IronicClient | None = None,
):
    """Update Ironic baremetal ports to match interfaces indicated by BMC."""
    device_uuid: str = ironic_node.uuid
    if ironic_client is None:
        ironic_client = IronicClient()
    logger.info("Syncing Interfaces / Ports for Device %s ...", device_uuid)

    discovered_ports = dict_by_mac_address(
        make_port_infos(
            interfaces=discovered_interfaces,
            pxe_interface_name=pxe_interface_name,
            device_name=ironic_node.name,
            device_uuid=device_uuid,
        )
    )
    logger.debug("Actual ports according to BMC: %s", discovered_ports)

    logger.info("Fetching Ironic Ports ...")
    ironic_ports = dict_by_mac_address(ironic_client.list_ports(device_uuid))

    for mac_address, ironic_port in ironic_ports.items():
        if mac_address not in discovered_ports:
            logger.info(
                "Server Interface %s no longer exists, "
                "deleting corresponding Ironic Port %s",
                mac_address,
                ironic_port.uuid,
            )
            response = ironic_client.delete_port(ironic_port.uuid)
            logger.debug("Deleted: %s", response)

    for mac_address, actual_port in discovered_ports.items():
        ironic_port = ironic_ports.get(mac_address)
        if ironic_port:
            patch = get_patch(actual_port, ironic_port)
            if patch:
                logger.info("Updating Ironic Port %s, setting %s", ironic_port, patch)
                response = ironic_client.update_port(ironic_port.uuid, patch)
                logger.debug("Updated: %s", response)
            else:
                logger.debug("No changes required for Ironic Port %s", mac_address)
        else:
            logger.info("Creating Ironic Port %s ...", actual_port)
            response = ironic_client.create_port(actual_port.dict())
            logger.debug("Created: %s", response)


def dict_by_mac_address(items: list) -> dict:
    return {item.address: item for item in items}


def make_port_infos(
    interfaces: list[InterfaceInfo],
    pxe_interface_name: str,
    device_uuid: str,
    device_name: str,
) -> list[PortConfiguration]:
    """Convert InterfaceInfo into PortConfiguration

    Excludes BMC interfaces and interfaces without a MAC address.

    Adds local_link and physical_network for interfaces that are connected to a
    "network" switch.
    """
    return [
        port_configuration(interface, pxe_interface_name, device_uuid, device_name)
        for interface in interfaces
        if (
            interface.mac_address
            and interface.name != "iDRAC"
            and interface.name != "iLo"
        )
    ]


def port_configuration(
    interface: InterfaceInfo,
    pxe_interface_name: str,
    device_uuid: str,
    device_name: str,
) -> PortConfiguration:
    # Interface names have device name prepended because Ironic wants them
    # globally unique across all devices.
    name = f"{device_name}:{interface.name}"
    pxe_enabled = interface.name == pxe_interface_name
    physical_network = None
    local_link_connection = {}

    if interface.remote_switch_mac_address and interface.remote_switch_port_name:
        switch = data_center.switch_for_mac(
            interface.remote_switch_mac_address, interface.remote_switch_port_name
        )
        if str(switch.vlan_group_name).endswith("-network"):
            physical_network = switch.vlan_group_name
            local_link_connection = {
                "switch_id": interface.remote_switch_mac_address.lower(),
                "port_id": interface.remote_switch_port_name,
                "switch_info": switch.name,
            }

    return PortConfiguration(
        node_uuid=device_uuid,
        address=interface.mac_address.lower(),
        name=name,
        pxe_enabled=pxe_enabled,
        local_link_connection=local_link_connection,
        physical_network=physical_network,
    )


def get_patch(nautobot_port: PortConfiguration, ironic_port: Port) -> list[dict]:
    """Generate patch to change data in format expected by Ironic API.

    Compare attributes between Port objects and return a patch object
    containing any changes.
    """
    return [
        {"op": "replace", "path": f"/{key}", "value": required_value}
        for key, required_value in dict(nautobot_port).items()
        if getattr(ironic_port, key) != required_value
    ]
