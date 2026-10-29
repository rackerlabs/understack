# pylint: disable=E1131,C0103

import argparse
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
    """Use minimal enrollment to test post-enrollment workflows.

    Read chassis info, create or update the Ironic node, then provide it and
    return its UUID. BMC configuration, inspection, BIOS, RAID, and firmware
    updates are skipped. The existing CLI arguments remain accepted for Argo.
    """
    helpers.setup_logger()
    args = argument_parser().parse_args()

    node_uuid = enroll(
        ip_address=args.ip_address,
        old_password=args.old_password,
        firmware_update=args.firmware_update,
        raid_configure=args.raid_configure,
        external_cmdb_id=args.external_cmdb_id,
    )

    if args.node_uuid_output:
        Path(args.node_uuid_output).write_text(node_uuid + "\n")


def enroll(
    ip_address: str,
    firmware_update: bool,
    raid_configure: bool,
    old_password: str | None,
    external_cmdb_id: int | str | None = None,
) -> str:
    logger.info(
        "Starting minimal test enroll workflow for bmc_ip_address=%s", ip_address
    )

    if external_cmdb_id:
        logger.info("  external_cmdb_id=%s", external_cmdb_id)

    bmc = bmc_for_ip_address(ip_address)
    device_info = chassis_info(bmc)

    node = ironic_node.create_or_update(
        bmc=bmc,
        name=device_name(device_info),
        manufacturer=device_info.manufacturer,
        external_cmdb_id=external_cmdb_id,
    )

    ironic_node.transition(node, target_state="provide", expected_state="available")
    logger.info(
        "Completed minimal test enroll workflow for bmc_ip_address=%s", ip_address
    )
    return str(node.uuid)


def device_name(device_info: ChassisInfo) -> str:
    return f"{device_info.manufacturer}-{device_info.serial_number}"


def parse_bool(value: str) -> bool:
    return value.lower() == "true"


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
