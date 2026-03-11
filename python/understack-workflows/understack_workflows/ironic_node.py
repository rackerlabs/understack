import logging

import ironicclient.common.apiclient.exceptions
from ironicclient.common.utils import args_array_to_patch

from understack_workflows.bmc import Bmc
from understack_workflows.ironic.client import IronicClient
from understack_workflows.node_configuration import IronicNodeConfiguration

STATES_ALLOWING_UPDATES = ["enroll", "manageable"]

logger = logging.getLogger(__name__)


def create_or_update(
    bmc: Bmc, name: str, manufacturer: str, external_cmdb_id: str | None = None
) -> IronicNodeConfiguration:
    """Note interfaces/ports are not synced here, that happens elsewhere."""
    client = IronicClient()
    driver, inspect_interface = _driver_for(manufacturer)

    try:
        ironic_node = client.get_node(name)
        logger.debug(
            "Using existing baremetal node %s with name %s", ironic_node.uuid, name
        )
        update_ironic_node(
            client, bmc, ironic_node, name, driver, inspect_interface, external_cmdb_id
        )
        # Return node as IronicNodeConfiguration (duck typing - Node has same attrs)
        return ironic_node  # type: ignore[return-value]
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug("Baremetal Node with name %s not found in Ironic, creating.", name)
        return create_ironic_node(
            client, bmc, name, driver, inspect_interface, external_cmdb_id
        )


def update_ironic_node(
    client,
    bmc,
    ironic_node,
    name,
    driver,
    inspect_interface,
    external_cmdb_id: str | None = None,
):
    if ironic_node.provision_state not in STATES_ALLOWING_UPDATES:
        logger.info(
            "Baremetal node %s is in %s provision_state, so no updates are allowed",
            ironic_node.uuid,
            ironic_node.provision_state,
        )
        return

    updates = [
        f"name={name}",
        f"driver={driver}",
        f"driver_info/redfish_address={bmc.url()}",
        "driver_info/redfish_verify_ca=false",
        f"driver_info/redfish_username={bmc.username}",
        f"driver_info/redfish_password={bmc.password}",
        "boot_interface=http-ipxe",
        f"inspect_interface={inspect_interface}",
    ]

    # Update external_cmdb_id only when explicitly provided
    if external_cmdb_id:
        updates.append(f"extra/external_cmdb_id={external_cmdb_id}")

    patches = args_array_to_patch("add", updates)
    logger.info("Updating Ironic node %s patches=%s", ironic_node.uuid, patches)

    response = client.update_node(ironic_node.uuid, patches)
    logger.info("Ironic node %s Updated: response=%s", ironic_node.uuid, response)


def create_ironic_node(
    client: IronicClient,
    bmc: Bmc,
    name: str,
    driver: str,
    inspect_interface: str,
    external_cmdb_id: str | None = None,
) -> IronicNodeConfiguration:
    node_data = {
        "name": name,
        "driver": driver,
        "driver_info": {
            "redfish_address": bmc.url(),
            "redfish_verify_ca": False,
            "redfish_username": bmc.username,
            "redfish_password": bmc.password,
        },
        "boot_interface": "http-ipxe",
        "inspect_interface": inspect_interface,
    }
    if external_cmdb_id:
        node_data["extra"] = {"external_cmdb_id": external_cmdb_id}
    # Return node as IronicNodeConfiguration (duck typing - Node has same attrs)
    return client.create_node(node_data)  # type: ignore[return-value]


def _driver_for(manufacturer: str) -> tuple[str, str]:
    """Answer the (driver, inspect_interface) for this server."""
    if manufacturer.startswith("Dell"):
        return ("idrac", "idrac-redfish")
    else:
        return ("redfish", "redfish")
