import argparse
import logging
import os
from uuid import UUID

import pynautobot
from ironicclient.v1.port import Port

from understack_workflows.ironic.client import IronicClient
from understack_workflows.port_configuration import PortConfiguration

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_nautobot_interfaces(device_id: UUID) -> list[PortConfiguration]:
    """Provides Nautobot to Ironic ports.

    Return a List of Ironic Ports for all Nautobot Interfaces with a
    MAC address, for the specified Device.
    """
    nautobot_api = os.environ["NAUTOBOT_API"]
    nautobot_token = os.environ["NAUTOBOT_TOKEN"]
    nautobot = pynautobot.api(nautobot_api, nautobot_token)
    interfaces = nautobot.dcim.interfaces.filter(device_id=device_id)

    ports = []
    for i in interfaces:
        if i.mac_address:
            ports.append(
                PortConfiguration(
                    node_uuid=str(device_id), address=i.mac_address, uuid=i.id
                )
            )
    return ports


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


def main():
    parser = argparse.ArgumentParser(
        description="Update Ironic ports from Nautobot Interfaces"
    )
    parser.add_argument(
        "--device-id",
        required=True,
        help="Ironic Node and Nautobot Device ID",
        type=UUID,
    )
    parser.add_argument(
        "--debug",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.WARNING,
    )
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction)
    args = parser.parse_args()

    device_id = args.device_id
    dry_run = args.dry_run
    logger.setLevel(args.loglevel)

    logger.info(f"Syncing Interfaces / Ports for Device {device_id} ...")

    # build ports from nautobot interfaces
    logger.info("Fetching Nautobot Interfaces ...")
    nautobot_ports = get_nautobot_interfaces(device_id)

    # get Ironic Ports
    client = IronicClient(
        svc_url=os.environ["IRONIC_SVC_URL"],
        username=os.environ["IRONIC_USERNAME"],
        password=os.environ["IRONIC_PASSWORD"],
        auth_url=os.environ["IRONIC_AUTH_URL"],
        tenant_name=os.environ["IRONIC_TENANT"],
    )

    logger.info("Fetching Ironic Ports ...")
    ironic_ports = client.list_ports(device_id)

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
                response = client.update_port(n.uuid, patch)
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
            response = client.create_port(p.dict())
            logger.debug(f"Created: {response}")

    # Delete stale Ironic Ports
    for i in ironic_ports:
        logger.debug(f"[ - ] {i}")
        if not dry_run:
            logger.info(
                f"Nautobot Interface {i.uuid} no longer exists, deleting "
                f"corresponding Ironic Port"
            )
            response = client.delete_port(i.uuid)
            logger.debug(f"Deleted: {response}")


if __name__ == "__main__":
    main()
