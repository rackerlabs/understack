import argparse
import os
import sys

from understack_workflows.helpers import boolean_args
from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.undersync.client import Undersync


def call_undersync(args):
    undersync_token = credential("undersync", "token")
    if not undersync_token:
        logger.error("Please provide auth token for Undersync.")
        sys.exit(1)

    undersync = Undersync(undersync_token)

    try:
        logger.debug(
            f"Syncing switches in vlan group {args.vlan_group_uuid} "
            f"{args.dry_run=} {args.force=}"
        )
        return undersync.sync_devices(
            args.vlan_group_uuid,
            dry_run=args.dry_run,
            force=args.force,
        )
    except Exception as error:
        logger.error(error)
        sys.exit(2)


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Trigger undersync run for a set of switches.",
    )
    parser.add_argument(
        "--vlan_group_uuid",
        type=str,
        required=True,
        help="UUID of Nautobot VlanGroup containing the switches to Undersync",
    )
    parser.add_argument(
        "--force",
        type=boolean_args,
        help="Call Undersync's force endpoint",
        required=False,
    )
    parser.add_argument(
        "--dry-run",
        type=boolean_args,
        help="Call Undersync's dry-run endpoint",
        required=False,
    )

    return parser


def main():
    """Requests an Undersync run on a pair of switches."""
    args = argument_parser().parse_args()

    response = call_undersync(args)
    logger.info(f"Undersync returned: {response.json()}")


logger = setup_logger(__name__)
if __name__ == "__main__":
    main()
