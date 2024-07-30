from nautobot import Nautobot
from helpers import arg_parser
from helpers import credential
from helpers import setup_logger

logger = setup_logger(__name__)


def main():
    parser = arg_parser(__file__)
    args = parser.parse_args()

    default_nb_url = "http://nautobot-default.nautobot.svc.cluster.local"
    device_uuid = args.device_uuid
    field_name = args.field_name
    field_value = args.field_value
    nb_url = args.nautobot_url or default_nb_url
    nb_token = args.nautobot_token or credential("nb-token", "token")

    nautobot = Nautobot(nb_url, nb_token, logger=logger)
    nautobot.update_cf(device_uuid, field_name, field_value)


if __name__ == "__main__":
    main()
