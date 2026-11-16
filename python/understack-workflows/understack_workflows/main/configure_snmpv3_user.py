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


def configure_snmpv3_user(client: IronicClient, node_uuid: str) -> None:
    """Run the SNMP runbook on a manageable or active node."""
    node = get_idle_node(client, node_uuid)
    if node.maintenance:
        raise ValueError(f"Node {node_uuid} is in maintenance")
    if node.provision_state not in {"manageable", "active"}:
        raise ValueError(
            f"Cannot run the SNMP runbook from {node.provision_state!r}; "
            "expected manageable or active"
        )

    runbook = client.get_runbook(RUNBOOK)
    if not runbook.disable_ramdisk:
        raise ValueError(f"Runbook {RUNBOOK} must disable the ramdisk")
    traits = client.get_node_traits(node_uuid)
    if not set(traits).intersection(runbook.traits):
        raise ValueError(f"Node {node_uuid} has no matching trait for {RUNBOOK}")

    servicing = node.provision_state == "active"
    expected = "active" if servicing else "manageable"
    request_transition(
        client,
        node_uuid,
        "service" if servicing else "clean",
        expected,
        runbook=runbook.uuid,
    )
    client.wait_for_node_provision_state(node_uuid, expected)
    error = getattr(client.get_node(node_uuid), "last_error", None)
    if error:
        raise RuntimeError(f"SNMP runbook failed on node {node_uuid}: {error}")


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
