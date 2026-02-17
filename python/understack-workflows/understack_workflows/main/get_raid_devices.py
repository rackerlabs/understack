import argparse
import json
import logging
import logging.config
import os

from sushy import Sushy

from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

log_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "loggers": {
        "__main__": {"level": "INFO"},
        "understack_workflows": {"level": "INFO"},
        "sushy": {"level": "INFO"},
        "sushy.main": {"level": "INFO"},
        "sushy.resources.base": {"level": "INFO"},
        "sushy.connector": {"level": "INFO"},
        "urllib3.connectionpool": {"level": "INFO"},
    },
}

logging.config.dictConfig(log_config)


def main():
    """Export RAID details for a BMC using Sushy.

    - connect to the BMC using standard password

    -  Using Sushy, gather controller details:
       - controller name
       - list of drive references for raid configuration.

    - output json object response.
    """
    args = argument_parser().parse_args()

    ip_address = args.ip_address
    password = args.password or None
    logger.debug("%s starting for ip_address=%s", __file__, ip_address)

    bmc = bmc_for_ip_address(ip_address=ip_address, password=password)
    client = bmc.sushy()

    # argo workflows captures stdout as the results which we can use
    # to return the device UUID
    raid_config = parse_controller_details(client)
    json_details = build_raid_config(raid_config)
    print(json.dumps(json_details))


def argument_parser():
    """Parse runtime arguments."""
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__), description="Gather RAID Device info."
    )
    parser.add_argument("--ip-address", type=str, required=True, help="BMC IP")
    parser.add_argument(
        "--password", type=str, required=False, help="Custom Password", default=None
    )
    return parser


def parse_controller_details(client: Sushy) -> dict:
    """Parse available RAID controller details for execution."""
    result = {"controller": None, "physical_disks": []}
    system_objects = client.get_system_collection().get_members()
    system = system_objects[0]
    for c in system.storage.get_members():
        if "RAID" in c.identity:
            result["controller"] = c.identity
            for d in c.drives:
                result["physical_disks"].append(d.identity)
            break
    return result


def get_raid_type(disk_count: int) -> int:
    if disk_count < 2:
        return 0
    if disk_count > 2:
        return 5
    return 1


def build_raid_config(raid_config: dict):
    """Return a raid config supported by ironic for cleanup tasks."""
    raid_level = get_raid_type(len(raid_config["physical_disks"]))
    result = {
        "logical_disks": [
            {
                "controller": raid_config["controller"],
                "is_root_volume": True,
                "physical_disks": raid_config["physical_disks"],
                "raid_level": str(raid_level),
                "size_gb": "MAX",
            }
        ]
    }
    return result


if __name__ == "__main__":
    main()
