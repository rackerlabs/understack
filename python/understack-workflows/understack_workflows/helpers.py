import argparse
import logging
import pathlib
from functools import partial
from urllib.parse import urlparse

import sushy


def setup_logger(name: str | None = None, level: int = logging.DEBUG):
    """Standardize our logging.

    Configures the root logger to prefix messages with a timestamp
    and to output the log level we want to see by default.

    params:
    name: logger hierarchy or root logger
    level: default log level (DEBUG)
    """
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=level,
    )
    return logging.getLogger(name)


def boolean_args(val):
    normalised = str(val).upper()
    if normalised in ["YES", "TRUE", "T", "1"]:
        return True
    elif normalised in ["NO", "FALSE", "F", "N", "0"]:
        return False
    else:
        raise argparse.ArgumentTypeError("boolean expected")


def _valid_url(value):
    parsed = urlparse(value)
    if not all([parsed.scheme, parsed.netloc]):
        raise argparse.ArgumentTypeError(f"Invalid URL: '{value}'")
    return value


def parser_nautobot_args(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--nautobot_url",
        type=_valid_url,
        required=False,
        help="Nautobot API %(default)s",
        default="http://nautobot-default.nautobot.svc.cluster.local",
    )
    parser.add_argument("--nautobot_token", type=str, required=False)
    return parser


comma_list_args = partial(str.split, sep=",")


def credential(subpath, item):
    ref = pathlib.Path("/etc").joinpath(subpath).joinpath(item)
    with ref.open() as f:
        return f.read().strip()


def oob_sushy_session(oob_ip, oob_username, oob_password):
    return sushy.Sushy(
        f"https://{oob_ip}",
        username=oob_username,
        password=oob_password,
        verify=False,
    )


def is_off_board(interface):
    return "Embedded ALOM" in interface.location or "Embedded" not in interface.location
