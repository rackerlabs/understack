from ironicclient.v1.port import Port

from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.port_configuration import PortConfiguration

logger = setup_logger(__name__)


def from_nautobot_to_ironic(
    nautobot_data: dict, pxe_interface: str, ironic_client=None
):
    """Update Ironic ports to match information found in Nautobot Interfaces."""
    device_id = nautobot_data["id"]
    logger.info(f"Syncing Interfaces / Ports for Device {device_id} ...")

    nautobot_ports = dict_by_uuid(get_nautobot_interfaces(nautobot_data, pxe_interface))
    logger.info(f"{nautobot_ports}")

    if ironic_client is None:
        ironic_client = IronicClient()

    logger.info("Fetching Ironic Ports ...")
    ironic_ports = dict_by_uuid(ironic_client.list_ports(device_id))

    for port_id, interface in ironic_ports.items():
        if port_id not in nautobot_ports:
            logger.info(
                f"Nautobot Interface {interface.uuid} no longer exists, "
                f"deleting corresponding Ironic Port"
            )
            response = ironic_client.delete_port(interface.uuid)
            logger.debug(f"Deleted: {response}")

    for port_id, nb_port in nautobot_ports.items():
        if port_id in ironic_ports:
            patch = get_patch(nb_port, ironic_ports[port_id])
            if patch:
                logger.info(f"Updating Ironic Port {nb_port} ...")
                response = ironic_client.update_port(port_id, patch)
                logger.debug(f"Updated: {response}")
            else:
                logger.debug(f"No changes required for Ironic Port {port_id}")
        else:
            logger.info(f"Creating Ironic Port {nb_port} ...")
            response = ironic_client.create_port(nb_port.dict())
            logger.debug(f"Created: {response}")


def dict_by_uuid(items: list) -> dict:
    return {item.uuid: item for item in items}


def get_nautobot_interfaces(
    nautobot_data, pxe_interface: str
) -> list[PortConfiguration]:
    """Get Nautobot interfaces for a device.

    Returns a list of PortConfiguration

    Excludes interfaces with no MAC address

    """
    device_id = nautobot_data["id"]

    return [
        port_configuration(interface, pxe_interface, device_id)
        for interface in nautobot_data["interfaces"]
        if interface_is_relevant(interface)
    ]


def port_configuration(interface: dict, pxe_interface, device_id) -> PortConfiguration:
    # Interface names have their UUID prepended because Ironic wants them
    # globally unique across all devices.
    name = f"{interface['id']} {interface['name']}"
    pxe_enabled = interface["name"] == pxe_interface

    return PortConfiguration(
        node_uuid=device_id,
        address=interface["mac_address"],
        uuid=interface["id"],
        name=name,
        pxe_enabled=pxe_enabled,
    )


def interface_is_relevant(interface: dict) -> bool:
    name = interface["name"]
    return interface["mac_address"] and name != "iDRAC" and name != "iLo"


def get_patch(nautobot_port: PortConfiguration, port: Port) -> list:
    """Generate patch to change data.

    Compare attributes between Port objects and return a patch object
    containing any changes.
    """
    patch = []
    for a in nautobot_port.__fields__:
        new_value = getattr(nautobot_port, a)
        old_value = getattr(port, a)
        if new_value != old_value:
            patch.append({"op": "replace", "path": f"/{a}", "value": new_value})
    return patch
