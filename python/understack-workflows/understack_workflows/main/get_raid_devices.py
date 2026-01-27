import argparse
import logging
import os

import sushy

from understack_workflows.bmc_password_standard import standard_password
from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

logs = [
    "__main__",
    "sushy.main",
    "sushy.resources.base",
    "sushy.connector",
    "urllib3.connectionpool",
]
for log_name in logs:
    log = logging.getLogger(log_name)
    log.setLevel("INFO")


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
    logger.debug("%s starting for ip_address=%s", __file__, ip_address)

    client = client_for_ip_address(ip_address=ip_address)

    # argo workflows captures stdout as the results which we can use
    # to return the device UUID
    print(parse_controller_details(client))


def argument_parser():
    """Parse runtime arguments."""
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__), description="Gather RAID Device info."
    )
    parser.add_argument("--ip-address", type=str, required=True, help="BMC IP")
    parser.add_argument("--password", type=str, required=False, help="Custom Password")
    return parser


def parse_controller_details(client) -> dict:
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


def client_for_ip_address(
    ip_address: str, username: str = "root", password: str | None = None
) -> sushy.Sushy:
    """Retreive a Sushy session for BMC return as client object.

    If no password is supplied then we use a conventional BMC standard one
    which is derived from the IP address and the BMC_MASTER secret key.

    If no username is supplied then the username "root" is used.
    """
    if password is None:
        bmc_master = os.getenv("BMC_MASTER") or credential("bmc_master", "key")
        password = standard_password(ip_address, bmc_master)

    base_url = "https://" + ip_address
    client = sushy.Sushy(
        base_url=base_url, username=username, password=password, verify=False
    )
    return client


if __name__ == "__main__":
    main()
