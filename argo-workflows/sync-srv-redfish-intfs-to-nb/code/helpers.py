import argparse
import logging
import os
import sushy
import sys

logger = logging.getLogger(__name__)


def setup_logger(name):
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger


def arg_parser(name):
    parser = argparse.ArgumentParser(
        prog=os.path.basename(name), description="Nautobot Interface sync"
    )
    parser.add_argument("--hostname", required=True,
                        help="Nautobot device name")
    parser.add_argument("--oob_username", required=False, help="OOB username")
    parser.add_argument("--oob_password", required=False, help="OOB password")
    parser.add_argument("--nautobot_url", required=False)
    parser.add_argument("--nautobot_token", required=False)
    return parser


def exit_with_error(error):
    logger.error(error)
    sys.exit(1)


def credential(subpath, item):
    try:
        return open(f"/etc/{subpath}/{item}", "r").read().strip()
    except FileNotFoundError:
        exit_with_error(f"{subpath} {item} not found in mounted files")


def oob_sushy_session(oob_ip, oob_username, oob_password):
    try:
        return sushy.Sushy(
            f"https://{oob_ip}",
            username=oob_username,
            password=oob_password,
            verify=False,
        )
    except sushy.exceptions.ConnectionError as e:
        exit_with_error(e)


def is_off_board(interface):
    return (
        "Embedded ALOM" in interface.location
        or "Embedded" not in interface.location
    )
