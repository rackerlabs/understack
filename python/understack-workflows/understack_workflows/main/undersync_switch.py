import argparse
import logging
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
            "Syncing switches in vlan group %s args.dry_run=%s args.force=%s",
            args.physical_network,
            args.dry_run,
            args.force,
        )
        return undersync.sync_devices(
            args.physical_network,
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
        "--physical-network",
        type=str,
        required=True,
        help="Port physical_network / Nautobot VLANGroup",
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
    setup_logger()
    args = argument_parser().parse_args()

    response = call_undersync(args)
    logger.info("Undersync returned: %s", response.json())


logger = logging.getLogger(__name__)
if __name__ == "__main__":
    main()
