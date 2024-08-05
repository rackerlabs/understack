import sys

from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger
from understack_workflows.helpers import undersync_switch_parser
from understack_workflows.main.undersync import Undersync


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


def main():
    """Requests an Undersync run on a pair of switches."""
    parser = undersync_switch_parser(__file__)
    args = parser.parse_args()

    response = call_undersync(args, args.switch_uuids)
    logger.info(f"Undersync returned: {response.json()}")


logger = setup_logger(__name__)
if __name__ == "__main__":
    main()
