import os

from ironicclient.v1.port import Port

from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.port_configuration import PortConfiguration

logger = setup_logger(__name__)


def from_nautobot_to_ironic(nautobot_data: dict, pxe_interface: str, ironic_client=None):
    """Update Ironic ports to match information found in Nautobot Interfaces."""
    device_id = nautobot_data["id"]
    logger.info(f"Syncing Interfaces / Ports for Device {device_id} ...")

    nautobot_ports = get_nautobot_interfaces(nautobot_data, pxe_interface)
    logger.info(f"{nautobot_ports}")

    if ironic_client is None:
        ironic_client = IronicClient()

    logger.info("Fetching Ironic Ports ...")
    ironic_ports = ironic_client.list_ports(device_id)

    # Update existing Ironic Ports
    new_ports = []
    for n in nautobot_ports:
        # identify any matching Ironic Ports
        matching_port = None
        for i in ironic_ports:
            if n.uuid == i.uuid:
                matching_port = i

        # if a port doesn't already exist, we'll create it later
        if not matching_port:
            new_ports.append(n)
            continue

        # If a matching port was found, we will remove it from the ironic_ports
        # list. Once this loop completes, any remaining ports in ironic_ports will
        # be considered stale, and will be removed from Ironic
        ironic_ports.remove(matching_port)

        # if any data has changed on this interface, patch the matching ironic Port
        patch = get_patch(n, matching_port)
        if patch:
            logger.debug(f"[ | ] {n}")
            logger.info(f"Updating Ironic Port {n} ...")
            response = ironic_client.update_port(n.uuid, patch)
            logger.debug(f"Updated: {response}")
        else:
            logger.debug(
                f"Existing Ironic Port already matches Nautobot Interface {n.uuid}"
            )

    # Create new Ironic Ports
    for p in new_ports:
        logger.debug(f"[ + ] {p}")
        logger.info(f"Creating Ironic Port {p} ...")
        response = ironic_client.create_port(p.dict())
        logger.debug(f"Created: {response}")

    # Delete stale Ironic Ports
    for i in ironic_ports:
        logger.debug(f"[ - ] {i}")
        logger.info(
            f"Nautobot Interface {i.uuid} no longer exists, deleting "
            f"corresponding Ironic Port"
        )
        response = ironic_client.delete_port(i.uuid)
        logger.debug(f"Deleted: {response}")


def get_nautobot_interfaces(nautobot_data, pxe_interface: str) -> list[PortConfiguration]:
    """Get Nautobot interfaces for a device.

    Returns a list of PortConfiguration

    Excludes interfaces with no MAC address
    """
    device_id = nautobot_data["id"]

    return [
        PortConfiguration(
            node_uuid=device_id,
            address=interface["mac_address"],
            uuid=interface["id"],
            name=interface["name"],
            pxe_enabled=(interface["name"] == pxe_interface),
        )
        for interface in nautobot_data["interfaces"]
            if interface_is_relevant(interface)
    ]

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
