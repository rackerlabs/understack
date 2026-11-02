import argparse
import logging

from ironicclient.common.apiclient import exceptions
from tenacity import before_sleep_log
from tenacity import retry
from tenacity import retry_if_exception_type
from tenacity import stop_after_delay
from tenacity import wait_fixed

from understack_workflows import helpers
from understack_workflows.ironic.client import IronicClient

logger = logging.getLogger(__name__)
RUNBOOK = "bmc-configure-snmpv3-user"
CLEANING_POLICY_KEY = "obm_monitoring_automated_clean"
BUSY_STATES = {"cleaning", "clean wait", "servicing", "service wait"}


retry_conflicts = retry(
    retry=retry_if_exception_type(exceptions.Conflict),
    stop=stop_after_delay(600),
    wait=wait_fixed(10),
    before_sleep=before_sleep_log(logger, logging.INFO),
    reraise=True,
)


def _get_idle_node(client: IronicClient, node_uuid: str):
    node = client.get_node(node_uuid)
    if (
        getattr(node, "reservation", None)
        or node.target_power_state
        or (
            node.target_provision_state and not node.provision_state.endswith(" failed")
        )
    ):
        raise exceptions.Conflict(f"Node {node_uuid} is busy")
    return node


get_idle_node = retry_conflicts(_get_idle_node)


@retry_conflicts
def request_transition(client, node_uuid, action, source, **kwargs):
    node = _get_idle_node(client, node_uuid)
    if node.provision_state != source or node.maintenance:
        raise ValueError(f"Node {node_uuid} is no longer ready for {action}")
    client.set_node_provision_state(node_uuid, action, **kwargs)


def transition(client: IronicClient, node_uuid: str, action: str, expected: str):
    source = "available" if action == "manage" else "manageable"
    request_transition(client, node_uuid, action, source)
    client.wait_for_node_provision_state(node_uuid, expected)


@retry_conflicts
def suppress_cleaning(client, node_uuid):
    node = _get_idle_node(client, node_uuid)
    if node.provision_state != "available" or node.maintenance:
        raise ValueError(f"Node {node_uuid} is no longer available")
    if CLEANING_POLICY_KEY not in node.extra:
        client.update_node(
            node_uuid,
            [
                {
                    "op": "add",
                    "path": f"/extra/{CLEANING_POLICY_KEY}",
                    "value": node.automated_clean,
                },
                {"op": "replace", "path": "/automated_clean", "value": False},
            ],
        )


@retry_conflicts
def restore_cleaning_policy(client, node_uuid, providing):
    node = _get_idle_node(client, node_uuid)
    if (
        node.provision_state in BUSY_STATES
        or (providing and node.provision_state == "manageable")
        or (node.target_provision_state and node.provision_state != "clean failed")
    ):
        raise ValueError("Node has not settled")
    if CLEANING_POLICY_KEY in node.extra:
        client.update_node(
            node_uuid,
            [
                {
                    "op": "replace",
                    "path": "/automated_clean",
                    "value": node.extra[CLEANING_POLICY_KEY],
                },
                {"op": "remove", "path": f"/extra/{CLEANING_POLICY_KEY}"},
            ],
        )


def restore_available_node(client: IronicClient, node_uuid: str) -> None:
    node = client.get_node(node_uuid)
    providing = node.provision_state == "manageable"
    try:
        if providing:
            transition(client, node_uuid, "provide", "available")
    finally:
        try:
            restore_cleaning_policy(client, node_uuid, providing)
        except (exceptions.Conflict, ValueError) as exc:
            raise exceptions.Conflict(
                f"Node {node_uuid} has not finished returning to available; "
                "automated cleaning remains disabled. "
                "Rerun configure-snmpv3-user after it settles to restore its policy."
            ) from exc


def configure_snmpv3_user(client: IronicClient, node_uuid: str) -> None:
    """Run the SNMP runbook and preserve an available node's cleaning policy."""
    node = client.get_node(node_uuid)
    restoring_available = CLEANING_POLICY_KEY in node.extra
    try:
        if restoring_available and node.provision_state in BUSY_STATES:
            client.wait_for_node_provision_state(
                node_uuid, node.target_provision_state or "manageable"
            )
        node = get_idle_node(client, node_uuid)
        if node.maintenance:
            raise ValueError(f"Node {node_uuid} is in maintenance")
        if node.provision_state not in {"manageable", "available", "active"}:
            raise ValueError(
                f"Cannot run the SNMP runbook from {node.provision_state!r}; "
                "expected manageable, available, or active"
            )

        runbook = client.get_runbook(RUNBOOK)
        if not runbook.disable_ramdisk:
            raise ValueError(f"Runbook {RUNBOOK} must disable the ramdisk")
        traits = client.get_node_traits(node_uuid)
        if not set(traits).intersection(runbook.traits):
            raise ValueError(f"Node {node_uuid} has no matching trait for {RUNBOOK}")

        if node.provision_state == "available":
            if not restoring_available:
                suppress_cleaning(client, node_uuid)
                restoring_available = True
            transition(client, node_uuid, "manage", "manageable")

        servicing = node.provision_state == "active"
        request_transition(
            client,
            node_uuid,
            "service" if servicing else "clean",
            "active" if servicing else "manageable",
            runbook=runbook.uuid,
        )
        client.wait_for_node_provision_state(
            node_uuid, "active" if servicing else "manageable"
        )
        error = getattr(client.get_node(node_uuid), "last_error", None)
        if error:
            raise RuntimeError(f"SNMP runbook failed on node {node_uuid}: {error}")
    finally:
        if restoring_available:
            restore_available_node(client, node_uuid)


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configure BMC SNMPv3 through its Ironic runbook."
    )
    parser.add_argument("--node", required=True, help="Node name or UUID")
    return parser


def main() -> None:
    helpers.setup_logger()
    args = argument_parser().parse_args()
    client = IronicClient()
    node = client.get_node(args.node)
    configure_snmpv3_user(client, node.uuid)
    logger.info("SNMPv3 configured on node %s", node.uuid)


if __name__ == "__main__":
    main()
