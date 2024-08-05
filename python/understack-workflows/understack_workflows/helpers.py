import argparse
import logging
import os
import pathlib
from functools import partial

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
        level=logging.DEBUG,
    )
    return logging.getLogger(name)


def arg_parser(name):
    parser = argparse.ArgumentParser(
        prog=os.path.basename(name), description="Nautobot Interface sync"
    )
    parser.add_argument("--hostname", required=True, help="Nautobot device name")
    parser.add_argument("--oob_username", required=False, help="OOB username")
    parser.add_argument("--oob_password", required=False, help="OOB password")
    parser.add_argument("--nautobot_url", required=False)
    parser.add_argument("--nautobot_token", required=False)
    return parser


def undersync_switch_parser(name):
    parser = argparse.ArgumentParser(
        prog=os.path.basename(name),
        description="Trigger undersync run for a set of switches.",
    )
    parser.add_argument(
        "--switch_uuids",
        type=__comma_list,
        required=True,
        help="Comma separated list of UUIDs of the switches to Undersync",
    )
    parser.add_argument(
        "--force",
        type=__boolean_args,
        help="Call Undersync's force endpoint",
        required=False,
    )
    parser.add_argument(
        "--dry-run",
        type=__boolean_args,
        help="Call Undersync's dry-run endpoint",
        required=False,
    )

    return parser


def __boolean_args(val):
    normalised = str(val).upper()
    if normalised in ["YES", "TRUE", "T", "1"]:
        return True
    elif normalised in ["NO", "FALSE", "F", "N", "0"]:
        return False
    else:
        raise argparse.ArgumentTypeError("boolean expected")


__comma_list = partial(str.split, sep=",")


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
