import sys
from nautobot import Nautobot
from helpers import undersync_parser
from helpers import credential
from helpers import setup_logger
from undersync import Undersync

logger = setup_logger(__name__)

def update_nautobot(args) -> list[str]:
    default_nb_url = "http://nautobot-default.nautobot.svc.cluster.local"
    device_uuid = args.device_uuid
    field_name = 'connected_to_network'
    field_value = args.network_name
    nb_url = args.nautobot_url or default_nb_url

    nb_token = args.nautobot_token or credential("nb-token", "token")
    nautobot = Nautobot(nb_url, nb_token, logger=logger)
    logger.info(f"Updating Device {device_uuid} and moving it to '{field_value}' network.")
    nautobot.update_cf(device_uuid, field_name, field_value)
    logger.debug(f"Updated Device.{field_name} to {field_value}")
    switches = nautobot.uplink_switches(device_uuid)
    logger.info(f"Obtained switch IDs: {switches}")
    return switches

def call_undersync(args, switches):
    undersync_token = credential('undersync', 'token')
    if not undersync_token:
        logger.error("Please provide auth token for Undersync.")
        sys.exit(1)
    undersync = Undersync(undersync_token)

    try:
        return undersync.sync_devices(switches, dry_run=args.dry_run, force=args.force)
    except Exception as error:
        logger.error(error)
        sys.exit(2)

def main():
    """
    Updates Nautobot Device's 'connected_to_network' field and follows with
    request to Undersync service, requesting sync for all of the
    uplink_switches that the device is connected to.
    """
    parser = undersync_parser(__file__)
    args = parser.parse_args()

    switches = update_nautobot(args)
    for response in call_undersync(args, switches):
        logger.info(f"Undersync returned: {response.json()}")


if __name__ == "__main__":
    main()
