from ironicclient.v1.port import Port

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.nautobot_device import NautobotDevice
from understack_workflows.nautobot_device import NautobotInterface
from understack_workflows.port_configuration import PortConfiguration

logger = setup_logger(__name__)


def from_nautobot_to_ironic(
    nautobot_device: NautobotDevice, pxe_interface: str, ironic_client=None
):
    """Update Ironic ports to match information found in Nautobot Interfaces."""
    logger.info("Syncing Interfaces / Ports for Device %s ...", nautobot_device.id)

    nautobot_ports = dict_by_uuid(
        get_nautobot_interfaces(nautobot_device, pxe_interface)
    )
    logger.debug("%s", nautobot_ports)

    if ironic_client is None:
        ironic_client = IronicClient()

    logger.info("Fetching Ironic Ports ...")
    ironic_ports = dict_by_uuid(ironic_client.list_ports(nautobot_device.id))

    for port_id, interface in ironic_ports.items():
        if port_id not in nautobot_ports:
            logger.info(
                "Nautobot Interface %s no longer exists, "
                "deleting corresponding Ironic Port",
                interface.uuid,
            )
            response = ironic_client.delete_port(interface.uuid)
            logger.debug("Deleted: %s", response)

    for port_id, nb_port in nautobot_ports.items():
        if port_id in ironic_ports:
            patch = get_patch(nb_port, ironic_ports[port_id])
            if patch:
                logger.info("Updating Ironic Port %s ...", nb_port)
                response = ironic_client.update_port(port_id, patch)
                logger.debug("Updated: %s", response)
            else:
                logger.debug("No changes required for Ironic Port %s", port_id)
        else:
            logger.info("Creating Ironic Port %s ...", nb_port)
            response = ironic_client.create_port(nb_port.model_dump())
            logger.debug("Created: %s", response)


def dict_by_uuid(items: list) -> dict:
    return {item.uuid: item for item in items}


def get_nautobot_interfaces(
    nautobot_device: NautobotDevice, pxe_interface: str
) -> list[PortConfiguration]:
    """Get Nautobot interfaces for a device.

    Returns a list of PortConfiguration

    Excludes interfaces with no MAC address

    """
    return [
        port_configuration(interface, pxe_interface, nautobot_device)
        for interface in nautobot_device.interfaces
        if interface_is_relevant(interface)
    ]


def port_configuration(
    interface: NautobotInterface, pxe_interface: str, device: NautobotDevice
) -> PortConfiguration:
    # Interface names have their UUID prepended because Ironic wants them
    # globally unique across all devices.
    name = f"{device.name}:{interface.name}"
    pxe_enabled = interface.name == pxe_interface

    if interface.neighbor_chassis_mac:
        local_link_connection = {
            "switch_id": interface.neighbor_chassis_mac.lower(),
            "port_id": interface.neighbor_interface_name,
            "switch_info": interface.neighbor_device_name,
        }
    else:
        local_link_connection = {}

    return PortConfiguration(
        node_uuid=device.id,
        address=interface.mac_address.lower(),
        uuid=interface.id,
        name=name,
        pxe_enabled=pxe_enabled,
        local_link_connection=local_link_connection,
        physical_network=interface.vlan_group_name,
    )


def interface_is_relevant(interface: NautobotInterface) -> bool:
    return bool(
        interface.mac_address and interface.name != "iDRAC" and interface.name != "iLo"
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
