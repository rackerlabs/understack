import argparse
import logging
import logging.config
import os
import pathlib
from functools import partial
from urllib.parse import urlparse

OUTPUT_BASE_PATH = "/var/run/argo"


_NOISY_LOGGERS = [
    "ironicclient",
    "keystoneauth",
    "keystoneauth1",
    "stevedore",
    "sushy",
    "urllib3",
]


def setup_logger(level: int = logging.DEBUG) -> None:
    """Configure logging for a main entry point.

    Sets the root logger to the requested level and explicitly suppresses
    noisy third-party libraries to WARNING regardless of the requested level.

    Should only be called from main() entry points, not from library modules.
    Library modules should use logging.getLogger(__name__) directly.

    params:
    level: log level for the root logger (default: DEBUG)
    """
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    "datefmt": "%Y-%m-%d %H:%M:%S %z",
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                },
            },
            "loggers": {noisy: {"level": "WARNING"} for noisy in _NOISY_LOGGERS},
            "root": {
                "handlers": ["console"],
                "level": level,
            },
        }
    )


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
    default_value = os.getenv(
        "NAUTOBOT_URL", "http://nautobot-default.nautobot.svc.cluster.local"
    )
    parser.add_argument(
        "--nautobot_url",
        type=_valid_url,
        required=False,
        help="Nautobot API %(default)s",
        default=default_value,
    )
    parser.add_argument("--nautobot_token", type=str, required=False)
    return parser


comma_list_args = partial(str.split, sep=",")


def credential(subpath, item):
    ref = pathlib.Path("/etc").joinpath(subpath).joinpath(item)
    with ref.open() as f:
        return f.read().strip()


def save_output(name, value):
    with open(f"{OUTPUT_BASE_PATH}/output.{name}", "w") as f:
        return f.write(value)
