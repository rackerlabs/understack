import argparse
import logging
import os
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
        prog=os.path.basename(name),
        description="Ironic to Nautobot provisioning state sync",
    )
    parser.add_argument("--device_uuid", required=True, help="Nautobot device UUID")
    parser.add_argument("--field-name", required=True)
    parser.add_argument("--field-value", required=True)
    parser.add_argument("--nautobot_url", required=False)
    parser.add_argument("--nautobot_token", required=False)

    return parser


def undersync_parser(name):
    parser = argparse.ArgumentParser(
        prog=os.path.basename(name), description="Trigger undersync run for a device"
    )
    parser.add_argument("--device_uuid", required=True, help="Nautobot device UUID")
    parser.add_argument("--network-name", required=True)
    parser.add_argument("--nautobot_url", required=False)
    parser.add_argument("--nautobot_token", required=False)
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


def exit_with_error(error):
    logger.error(error)
    sys.exit(1)


def credential(subpath, item):
    try:
        return open(f"/etc/{subpath}/{item}", "r").read().strip()
    except FileNotFoundError:
        exit_with_error(f"{subpath} {item} not found in mounted files")
