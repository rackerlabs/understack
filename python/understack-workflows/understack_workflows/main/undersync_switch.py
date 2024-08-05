import argparse
import os
import sys

from understack_workflows.helpers import boolean_args
from understack_workflows.helpers import comma_list_args
from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.undersync.client import Undersync


def call_undersync(args, switches):
    undersync_token = credential("undersync", "token")
    if not undersync_token:
        logger.error("Please provide auth token for Undersync.")
        sys.exit(1)
    undersync = Undersync(undersync_token)

    try:
        logger.debug(f"Syncing switches: {switches} {args.dry_run=} {args.force=}")
        return undersync.sync_devices(switches, dry_run=args.dry_run, force=args.force)
    except Exception as error:
        logger.error(error)
        sys.exit(2)


def argument_parser():
    parser = argparse.ArgumentParser(
        prog=os.path.basename(__file__),
        description="Trigger undersync run for a set of switches.",
    )
    parser.add_argument(
        "--switch_uuids",
        type=comma_list_args,
        required=True,
        help="Comma separated list of UUIDs of the switches to Undersync",
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

    response = call_undersync(args, args.switch_uuids)
    logger.info(f"Undersync returned: {response.json()}")


logger = setup_logger(__name__)
if __name__ == "__main__":
    main()
