import json
import logging
from collections.abc import Sequence

import ironicclient.common.apiclient.exceptions
from ironicclient.common.utils import args_array_to_patch
from ironicclient.v1.node import Node

from understack_workflows.bmc import Bmc
from understack_workflows.ironic.client import IronicClient

FIRMWARE_UPDATE_TRAIT_PREFIX = "CUSTOM_FIRMWARE_UPDATE_"
ENROLLABLE_STATES = {"clean failed", "inspect failed", "enroll", "manageable"}

logger = logging.getLogger(__name__)


def create_or_update(
    bmc: Bmc,
    name: str,
    manufacturer: str,
    external_cmdb_id: str | None = None,
    enrolled_pxe_ports: list[str] | None = None,
) -> Node:
    """Find-or-create Node by name, update attributes, set state to Manageable.

    If the node exists in a quiescent state like "clean failed" then we will set
    it to "manageable" state before proceeding to update the node attributes.

    If the node exists in a "busy" state then we raise an exception.

    If the node does not already exist it is created and then transitioned from
    enrol->manageable state.

    Note interfaces/ports are not synced here, that happens elsewhere.
    """
    client = IronicClient()
    driver, inspect_interface = _driver_for(manufacturer)

    try:
        node = client.get_node(name)
        logger.debug(
            "Baremetal node %s already exists with name %s in provision_state %s",
            node.uuid,
            name,
            node.provision_state,
        )

        if node.provision_state not in ENROLLABLE_STATES:
            raise Exception(
                f"Re-enrol cannot proceed unless node is in one of the states "
                f"{sorted(ENROLLABLE_STATES)} but node {node.uuid} "
                f"is in '{node.provision_state}'."
            )

        if node.provision_state != "manageable":
            transition(node, target_state="manage", expected_state="manageable")

        update_ironic_node(
            client,
            bmc,
            node,
            name,
            driver,
            inspect_interface,
            external_cmdb_id,
            enrolled_pxe_ports,
        )
    except ironicclient.common.apiclient.exceptions.NotFound:
        logger.debug("Baremetal Node with name %s not found in Ironic, creating.", name)
        node = create_ironic_node(
            client,
            bmc,
            name,
            driver,
            inspect_interface,
            external_cmdb_id,
            enrolled_pxe_ports,
        )
        # All newly-created nodes start out with "enrol" state:
        transition(node, target_state="manage", expected_state="manageable")

    return node


def update_ironic_node(
    client,
    bmc,
    ironic_node,
    name,
    driver,
    inspect_interface,
    external_cmdb_id: str | None = None,
    enrolled_pxe_ports: list[str] | None = None,
):
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
    if enrolled_pxe_ports is not None:
        payload = json.dumps(enrolled_pxe_ports)
        updates.append(f"extra/enrolled_pxe_ports={payload}")

    patches = args_array_to_patch("add", updates)
    logger.info("Updating Ironic node %s patches=%s", ironic_node.uuid, patches)

    client.update_node(ironic_node.uuid, patches)
    logger.debug("Ironic node %s Updated.")


def create_ironic_node(
    client: IronicClient,
    bmc: Bmc,
    name: str,
    driver: str,
    inspect_interface: str,
    external_cmdb_id: str | None = None,
    enrolled_pxe_ports: list[str] | None = None,
) -> Node:
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
    if external_cmdb_id or enrolled_pxe_ports is not None:
        node_data["extra"] = {}
    if external_cmdb_id:
        node_data["extra"]["external_cmdb_id"] = external_cmdb_id
    if enrolled_pxe_ports is not None:
        node_data["extra"]["enrolled_pxe_ports"] = enrolled_pxe_ports

    if driver == "fake-hardware":
        node_data["resource_class"] = "fakehw"

    return client.create_node(node_data)


def _driver_for(manufacturer: str) -> tuple[str, str]:
    """Answer the (driver, inspect_interface) for this server."""
    if manufacturer.startswith("Dell"):
        return ("idrac", "idrac-redfish")
    else:
        return ("redfish", "redfish")


def transition(
    node: Node,
    target_state: str,
    expected_state: str | None = None,
    clean_steps: list[dict] | None = None,
    runbook: str | None = None,
    disable_ramdisk: bool | None = None,
) -> None:
    client = IronicClient()

    logger.info("%s requesting provision state %s", node.uuid, target_state)
    client.set_node_provision_state(
        node.uuid,
        target_state,
        clean_steps=clean_steps,
        runbook=runbook,
        disable_ramdisk=disable_ramdisk,
    )
    if expected_state:
        logger.info(
            "Waiting for node %s to enter provision state %s",
            node.uuid,
            expected_state,
        )
        client.wait_for_node_provision_state(node.uuid, expected_state, timeout=1800)


def patch(node: Node, updates: Sequence[str]) -> None:
    if not updates:
        return
    logger.info("%s updating node %s", node.uuid, list(updates))
    IronicClient().update_node(node.uuid, args_array_to_patch("add", list(updates)))


def set_target_raid_config(node: Node, raid_config: dict) -> None:
    IronicClient().set_node_target_raid_config(node.uuid, raid_config)


def inspect_out_of_band(node: Node):
    intf_reset = args_array_to_patch("remove", ["inspect_interface"])
    logger.info("[node:%s] Resetting to redfish interface", node.uuid)
    IronicClient().update_node(node.uuid, intf_reset)
    logger.info("[node:%s] Performing out-of-band inspection", node.uuid)
    transition(node, target_state="inspect", expected_state="manageable")


def inspect(node: Node, inspect_interface: str = "agent"):
    """Set the node inspect interface, inspect and wait for success.

    We raise an error if anything failed.  If we return then the everything has
    succeeded and the node has returned to the manageable state.
    """
    refreshed_node = refresh(node, fields=["inspect_interface"])
    if refreshed_node.inspect_interface != inspect_interface:
        patch(node, [f"inspect_interface={inspect_interface}"])

    transition(node, target_state="inspect", expected_state="manageable")


def apply_firmware_updates(node: Node) -> None:
    client = IronicClient()
    traits = client.get_node_traits(node.uuid)
    update_traits = sorted(
        (trait for trait in traits if trait.startswith(FIRMWARE_UPDATE_TRAIT_PREFIX)),
        key=firmware_trait_sort_key,
    )
    if not update_traits:
        logger.info("%s No firmware update traits found", node.uuid)
        return

    for trait in update_traits:
        runbook = client.get_runbook(trait)
        logger.info("%s Running firmware update trait %s", node.uuid, trait)
        transition(
            node,
            "clean",
            expected_state="manageable",
            runbook=runbook.uuid,
        )


def firmware_trait_sort_key(trait: str) -> tuple[int, str]:
    parts = trait.split("_")
    order = parts[3] if len(parts) > 3 else ""
    if order.isdigit():
        return (int(order), trait)
    return (10**9, trait)


def refresh(node: Node, fields: list[str] | None = None) -> Node:
    return IronicClient().get_node(node.uuid, fields=fields)
