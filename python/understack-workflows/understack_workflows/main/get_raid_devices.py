import argparse
import json
import logging
import os

from sushy import Sushy

from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.helpers import setup_logger

logger = logging.getLogger(__name__)


def main():
    """Export RAID details for a BMC using Sushy.

    - connect to the BMC using standard password

    -  Using Sushy, gather controller details:
       - controller name
       - list of drive references for raid configuration.

    - output json object response.
    """
    setup_logger()
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
    system = system_objects.pop()
    for c in system.storage.get_members():
        if "RAID" in c.identity.upper():
            result["controller"] = c.identity
            for d in c.drives:
                capacity = d.capacity_bytes / (10**9)
                result["physical_disks"].append(
                    {"name": d.identity, "size_gb": f"{capacity:.0f}"}
                )
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
    sizes = sorted({int(d["size_gb"]) for d in raid_config["physical_disks"]})
    base_config = {"logical_disks": []}
    for size in sizes:
        _root_vol = bool(size == sizes[0]) or bool(
            len(sizes) == 1
        )  # First size or only size.
        disks = [
            d["name"]
            for d in raid_config["physical_disks"]
            if int(d["size_gb"]) == size
        ]
        raid_level = get_raid_type(len(disks))
        base_config["logical_disks"].append(
            {
                "controller": raid_config["controller"],
                "is_root_volume": _root_vol,
                "physical_disks": disks,
                "raid_level": str(raid_level),
                "size_gb": "MAX",
            }
        )
    return base_config


if __name__ == "__main__":
    main()
