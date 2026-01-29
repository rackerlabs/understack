import argparse
import json
import logging.config
import logging
import os

import sushy

from understack_workflows.bmc import Bmc
from understack_workflows.bmc import bmc_for_ip_address
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)

log_config = {
  'version': 1,
  'disable_existing_loggers': False,
  'loggers': {
    "__main__": {'level': 'INFO'},
    "sushy.main": {'level': 'INFO'},
    "sushy.resources.base": {'level': 'INFO'},
    "sushy.connector": {'level': 'INFO'},
    "urllib3.connectionpool": {'level': 'INFO'},
  }
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
    print(json.dumps(parse_controller_details(client)))


def argument_parser():
    """Parse runtime arguments."""
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__), description="Gather RAID Device info."
    )
    parser.add_argument("--ip-address", type=str, required=True, help="BMC IP")
    parser.add_argument("--password", type=str, required=False, help="Password", default=None)
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


if __name__ == "__main__":
    main()
