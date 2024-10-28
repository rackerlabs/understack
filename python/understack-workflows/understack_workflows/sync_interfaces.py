import os
from uuid import UUID

import pynautobot
from ironicclient.v1.port import Port

from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.ironic.client import IronicClient
from understack_workflows.port_configuration import PortConfiguration

logger = setup_logger(__name__)


def from_nautobot_to_ironic(device_id: str, dry_run=False, ironic_client=None):
    """Update Ironic ports to match information found in Nautobot Interfaces."""
    logger.info(f"Syncing Interfaces / Ports for Device {device_id} ...")

    nautobot_api = os.environ.get("NAUTOBOT_API")
    nautobot_token = os.environ.get("NAUTOBOT_TOKEN") or credential("nb-token", "token")
    nautobot = pynautobot.api(nautobot_api, nautobot_token)

    logger.info("Fetching Nautobot Interfaces ...")
    nautobot_ports = get_nautobot_interfaces(nautobot, device_id)

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
            if str(n.uuid) == i.uuid:
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
            if not dry_run:
                logger.info(f"Updating Ironic Port {n} ...")
                response = ironic_client.update_port(n.uuid, patch)
                logger.debug(f"Updated: {response}")
        else:
            logger.debug(
                f"An existing Ironic Port was found for Nautobot Interface {n.uuid}"
            )

    # Create new Ironic Ports
    for p in new_ports:
        logger.debug(f"[ + ] {p}")
        if not dry_run:
            logger.info(f"Creating Ironic Port {p} ...")
            response = ironic_client.create_port(p.dict())
            logger.debug(f"Created: {response}")

    # Delete stale Ironic Ports
    for i in ironic_ports:
        logger.debug(f"[ - ] {i}")
        if not dry_run:
            logger.info(
                f"Nautobot Interface {i.uuid} no longer exists, deleting "
                f"corresponding Ironic Port"
            )
            response = ironic_client.delete_port(i.uuid)
            logger.debug(f"Deleted: {response}")


def get_nautobot_interfaces(nautobot, device_id: UUID) -> list[PortConfiguration]:
    """Get Nautobot interfaces for a device.

    Returns a list of PortConfiguration

    Excludes interfaces with no MAC address
    """
    interfaces = nautobot.dcim.interfaces.filter(device_id=device_id)

    return [
        PortConfiguration(
            node_uuid=str(device_id), address=i.mac_address, uuid=i.id, name=i.name
        )
        for i in interfaces
        if i.mac_address
    ]


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
