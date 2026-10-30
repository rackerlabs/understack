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


@retry(
    retry=retry_if_exception_type(exceptions.Conflict),
    stop=stop_after_delay(600),
    wait=wait_fixed(10),
    before_sleep=before_sleep_log(logger, logging.INFO),
    reraise=True,
)
def configure_snmpv3_user(client: IronicClient, node_uuid: str, slot: int) -> None:
    """Wait for contention to clear, then configure SNMP without transitions."""
    client.client.node.vendor_passthru(
        node_uuid,
        "configure_snmpv3_user",
        args={"slot": slot},
        http_method="POST",
    )


def argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Configure BMC SNMPv3 without changing Ironic node state."
    )
    parser.add_argument("--node", required=True, help="Node name or UUID")
    parser.add_argument("--slot", type=int, choices=range(3, 17), default=5)
    return parser


def main() -> None:
    helpers.setup_logger()
    args = argument_parser().parse_args()
    client = IronicClient()
    node = client.get_node(args.node)
    configure_snmpv3_user(client, node.uuid, args.slot)
    logger.info("SNMPv3 configured on node %s", node.uuid)


if __name__ == "__main__":
    main()
