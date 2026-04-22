import logging
from collections.abc import Sequence
from dataclasses import dataclass

import ironicclient.common.apiclient.exceptions
from ironicclient.common.utils import args_array_to_patch
from ironicclient.v1.node import Node

from understack_workflows.bmc import Bmc
from understack_workflows.ironic.client import IronicClient

FIRMWARE_UPDATE_TRAIT_PREFIX = "CUSTOM_FIRMWARE_UPDATE_"

STEADY_STATE_BOOT_INTERFACE = "http-ipxe"

_VIRTUAL_MEDIA_BOOT_INTERFACE = {
    "idrac": "idrac-redfish-virtual-media",
    "redfish": "redfish-virtual-media",
    "ilo": "ilo-virtual-media",
    "ilo5": "ilo-virtual-media",
    "fake-hardware": "fake",
}

# When performing a "clean" or "provide" operation, how long do we wait for
# Ironic to move the node its final state:
NODE_STATE_TIMEOUT_SECS = 90 * 60


@dataclass
class NodeInterface:
    name: str
    mac_address: str
    speed_mbps: int


ENROLLABLE_STATES = {"clean failed", "inspect failed", "enroll", "manageable"}

logger = logging.getLogger(__name__)


def create_or_update(
    bmc: Bmc,
    name: str,
    manufacturer: str,
    external_cmdb_id: str | None = None,
) -> Node:
    """Find-or-create Node by name, update attributes, set state to Manageable.

    If the node exists in a quiescent state like "clean failed" then we will set
    it to "manageable" state before proceeding to update the node attributes.

    If the node exists in a "busy" state then we raise an exception.

    If the node does not already exist it is created and then transitioned from
    enroll->manageable state.

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
                f"Re-enroll cannot proceed unless node is in one of the states "
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
        )
        # All newly-created nodes start out with "enroll" state:
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
):
    updates = [
        f"name={name}",
        f"driver={driver}",
        f"driver_info/redfish_address={bmc.url()}",
        "driver_info/redfish_verify_ca=false",
        f"driver_info/redfish_username={bmc.username}",
        f"driver_info/redfish_password={bmc.password}",
        f"boot_interface={STEADY_STATE_BOOT_INTERFACE}",
        f"inspect_interface={inspect_interface}",
    ]

    if external_cmdb_id:
        updates.append(f"extra/external_cmdb_id={external_cmdb_id}")

    patches = args_array_to_patch("add", updates)
    logger.info("Updating Ironic node %s patches=%s", ironic_node.uuid, patches)

    client.update_node(ironic_node.uuid, patches)
    logger.debug("Ironic node %s Updated.", ironic_node.uuid)


def create_ironic_node(
    client: IronicClient,
    bmc: Bmc,
    name: str,
    driver: str,
    inspect_interface: str,
    external_cmdb_id: str | None = None,
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
        "boot_interface": STEADY_STATE_BOOT_INTERFACE,
        "inspect_interface": inspect_interface,
    }
    if external_cmdb_id:
        node_data["extra"] = {"external_cmdb_id": external_cmdb_id}

    if driver == "fake-hardware":
        node_data["resource_class"] = "fakehw"

    return client.create_node(node_data)


def clear_pending_idrac_jobs(node: Node):
    logger.info("%s performing clear_job_queue clean step", node.uuid)
    transition(
        node,
        target_state="clean",
        expected_state="manageable",
        clean_steps=[{"interface": "management", "step": "clear_job_queue"}],
        disable_ramdisk=True,
    )


def _driver_for(manufacturer: str) -> tuple[str, str]:
    """Answer the (driver, inspect_interface) for this server."""
    if manufacturer.startswith("Dell"):
        return ("idrac", "idrac-redfish")
    else:
        return ("redfish", "redfish")


def virtual_media_boot_interface_for(driver: str) -> str:
    """Return the virtual-media boot_interface name for this driver."""
    try:
        return _VIRTUAL_MEDIA_BOOT_INTERFACE[driver]
    except KeyError as exc:
        raise ValueError(
            f"No virtual-media boot_interface configured for driver {driver!r}"
        ) from exc


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
        client.wait_for_node_provision_state(
            node.uuid, expected_state, timeout=NODE_STATE_TIMEOUT_SECS
        )


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


def get_node_inventory(node: Node) -> dict:
    """Return the raw inventory dict populated by OOB inspection."""
    return IronicClient().get_node_inventory(node.uuid)


def get_node_interfaces(node: Node) -> list[NodeInterface]:
    """Return interfaces from the inventory populated by OOB inspection."""
    inventory_data = get_node_inventory(node)
    interfaces_raw = inventory_data.get("inventory", {}).get("interfaces", [])
    return [
        NodeInterface(
            name=iface["name"],
            mac_address=iface["mac_address"],
            speed_mbps=iface.get("speed_mbps", 0),
        )
        for iface in interfaces_raw
    ]


def list_node_ports(node: Node) -> list:
    """Return ironic ports for this node."""
    return list(IronicClient().list_ports(node.uuid))


def pxe_enabled_bios_name(node: Node) -> str | None:
    """BIOS-reported name of port currently flagged pxe_enabled.

    We don't count a port whose physical_network has the placeholder "enrol"
    value.

    extra.bios_name is populated by the port-bios-name inspection hook during
    out-of-band redfish inspection.

    pxe_enabled is populated by the port-enroll-config hook during agent
    inspection.
    """
    for port in list_node_ports(node):
        if (
            port.pxe_enabled
            and port.extra.get("bios_name")
            and port.physical_network != "enrol"
        ):
            return port.extra["bios_name"]


def get_lldp_connected_interfaces(
    interfaces: list[NodeInterface], parsed_lldp: dict
) -> list[NodeInterface]:
    """Return interfaces that have a confirmed LLDP switch connection.

    An interface is considered connected when it appears in ``parsed_lldp``
    with a ``switch_port_id`` that is not ``"Not Available"``.
    """
    return [
        iface
        for iface in interfaces
        if parsed_lldp.get(iface.name, {}).get("switch_port_id")
        not in (None, "Not Available")
    ]


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
