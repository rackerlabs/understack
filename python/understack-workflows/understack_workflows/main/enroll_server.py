# pylint: disable=E1131,C0103

import argparse
import json
import logging
import os
from pathlib import Path

from understack_workflows import helpers
from understack_workflows import ironic_node
from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.bmc_chassis_info import ChassisInfo
from understack_workflows.bmc_chassis_info import chassis_info

logger = logging.getLogger(__name__)


def main() -> None:
    """On-board a new baremetal node, or refresh an existing one.

    TRIMMED flow (branch `trim-enroll-post-inspection`): this build exercises
    ONLY the post_inspection_runbooks loop and the post-enroll hook. BMC
    initialization/password, out-of-band and agent inspection, Dell BIOS
    configuration, RAID, and firmware steps have been removed from the default
    enroll() flow. The remaining steps are:

    - From the BMC, read basic chassis info (manufacturer, serial) with a
      read-only Redfish query to derive the node name.

    - Find or create this baremetal node in Ironic:
      - Set the name to "{manufacturer}-{serial_number}".
      - Set the driver as appropriate for the manufacturer/model.
      - Set the node's external_cmdb_id, if one was provided.

    - Execute post-inspection runbooks in the supplied order.

    - Transition the node to the 'available' state (implies cleaning).

    - On success, write the node UUID to --node-uuid-output (consumed by the
      optional post-enroll hook).

    The --old-password, --firmware-update, and --raid-configure arguments are
    still parsed (the Argo template passes them) but are inert in the trimmed
    flow.
    """
    helpers.setup_logger()
    args = argument_parser().parse_args()

    node_uuid = enroll(
        ip_address=args.ip_address,
        old_password=args.old_password,
        firmware_update=args.firmware_update,
        raid_configure=args.raid_configure,
        external_cmdb_id=args.external_cmdb_id,
        post_inspection_runbooks=args.post_inspection_runbooks,
    )

    if args.node_uuid_output:
        Path(args.node_uuid_output).write_text(node_uuid + "\n")


def enroll(
    ip_address: str,
    firmware_update: bool,
    raid_configure: bool,
    old_password: str | None,
    external_cmdb_id: int | str | None = None,
    post_inspection_runbooks: list[str] | None = None,
) -> str:
    logger.info("Starting (trimmed) enroll workflow for bmc_ip_address=%s", ip_address)

    if external_cmdb_id:
        logger.info("  external_cmdb_id=%s", external_cmdb_id)

    bmc = bmc_for_ip_address(ip_address)
    # Read-only Redfish query to derive the node name. No BMC mutation.
    device_info = chassis_info(bmc)

    node = ironic_node.create_or_update(
        bmc=bmc,
        name=device_name(device_info),
        manufacturer=device_info.manufacturer,
        external_cmdb_id=external_cmdb_id,
    )

    for runbook in post_inspection_runbooks or []:
        ironic_node.run_post_inspection_runbook(node, runbook)

    ironic_node.transition(node, target_state="provide", expected_state="available")
    logger.info("Completed (trimmed) enroll workflow for bmc_ip_address=%s", ip_address)
    return str(node.uuid)


def device_name(device_info: ChassisInfo) -> str:
    return f"{device_info.manufacturer}-{device_info.serial_number}"


def parse_bool(value: str) -> bool:
    return value.lower() == "true"


def parse_runbooks(value: str) -> list[str]:
    """Parse an ordered JSON array of runbook names or UUIDs."""
    try:
        runbooks = json.loads(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "Expected a JSON array of runbook names or UUIDs"
        ) from exc
    if not isinstance(runbooks, list) or any(
        not isinstance(runbook, str) or not runbook.strip() for runbook in runbooks
    ):
        raise argparse.ArgumentTypeError(
            "Expected a JSON array of nonempty runbook names or UUIDs"
        )
    return runbooks


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Run the server enroll workflow",
    )
    parser.add_argument(
        "--node-uuid-output",
        help="Write node UUID to this file after successful enrollment",
    )
    parser.add_argument("--ip-address", required=True, help="IP Address of BMC")
    parser.add_argument(
        "--old-password",
        required=False,
        help="Old (current) BMC password",
    )
    parser.add_argument(
        "--post-inspection-runbooks",
        type=parse_runbooks,
        default=[],
        help=(
            "JSON array of runbook names or UUIDs to execute in order "
            "after inspection and BIOS configuration"
        ),
    )
    parser.add_argument(
        "--firmware-update",
        type=parse_bool,
        default=False,
        help="Run firmware update runbooks after inspection",
    )
    parser.add_argument(
        "--raid-configure",
        type=parse_bool,
        default=True,
        help="Configure RAID before inspection",
    )
    parser.add_argument(
        "--external-cmdb-id",
        type=helpers.int_or_str,
        required=False,
        default="",
        help="External CMDB ID for RXDB integration",
    )
    return parser


if __name__ == "__main__":
    main()
