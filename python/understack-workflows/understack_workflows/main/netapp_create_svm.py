import argparse
import configparser
import os

import urllib3
from netapp_ontap import utils
from netapp_ontap.error import NetAppRestError
from netapp_ontap.host_connection import HostConnection
from netapp_ontap.resources import Svm, Volume
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


# Suppress warnings for unverified HTTPS requests, common in lab environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def parse_ontap_config(config_path="/etc/netapp/config.ini"):
    """
    Reads ONTAP connection details from a specified INI configuration file.
    """
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found at {config_path}")
        exit(1)

    config = configparser.ConfigParser()
    config.read(config_path)

    try:
        logger.debug(
            f"Reading configuration from section [netapp_nvme] in {config_path}"
        )
        hostname = config.get("netapp_nvme", "netapp_server_hostname")
        login = config.get("netapp_nvme", "netapp_login")
        password = config.get("netapp_nvme", "netapp_password")
    except (configparser.NoSectionError, configparser.NoOptionError) as e:
        logger.error(f"Missing required configuration in {config_path}. Details: {e}")
        exit(1)

    return hostname, login, password


def create_svm(args):
    """Creates a new Storage Virtual Machine (SVM)."""
    name = f"os-{args.svm_name}"
    root_name = f"{name}_root"

    logger.info(f"Creating SVM: {name}...")
    try:
        svm = Svm(
            name=name,
            aggregates=[{"name": args.aggregate_name}],
            language="c.utf_8",
            root_volume={"name": root_name, "security_style": "unix"},
            allowed_protocols=["nvme"],
            nvme={"enabled": True},
        )
        svm.post()
        # Wait for SVM to be fully created and online
        svm.get()
        logger.info(f"SVM '{svm.name}' created successfully with NVMe protocol allowed")
    except NetAppRestError as e:
        logger.error(f"Error creating SVM: {e}")
        exit(1)


def create_volume(args):
    """Creates a new volume within a specific SVM and aggregate."""
    volume_name = f"vol_{args.svm_name}"
    volume_size_str = args.volume_size
    logger.info(
        f"Creating volume '{volume_name}' with size {volume_size_str} on aggregate '{args.aggregate_name}'..."
    )


    try:
        volume_name = f"vol_{args.svm_name}"
        volume = Volume(
            name=volume_name,
            svm={"name": f"os-{args.svm_name}"},
            aggregates=[{"name": args.aggregate_name}],
            size=args.volume_size,
        )
        volume.post()
        volume.get()
        logger.info(f"Volume {volume_name} created.")
    except NetAppRestError as e:
        logger.error(f"Error creating Volume: {e}")
        exit(1)


def argument_parser():
    parser = argparse.ArgumentParser(
        description="NetApp ONTAP SVM and Volume Creator via REST API",
        prog=os.path.basename(__file__),
    )
    parser.add_argument(
        "--svm_name", required=True, help="Name of the SVM to be created"
    )
    parser.add_argument(
        "--volume_size", required=True, help="Size of the volume (e.g., '1TB', '500GB')"
    )
    parser.add_argument(
        "--aggregate_name", required=True, help="Name of the aggregate for the volume"
    )
    parser.add_argument("--debug", help="Enable Debug", action="store_true")
    parser.add_argument(
        "--config_file",
        default="/etc/netapp/config.ini",
        help="Path to the configuration file",
    )

    return parser


def main():
    """
    Main function to orchestrate the SVM and volume creation process.
    """
    args = argument_parser().parse_args()
    logger.info("Starting ONTAP SVM and Volume creation workflow.")

    hostname, login, password = parse_ontap_config(args.config_file)
    auth = (login, password)

    do_action(auth, hostname, args)
    logger.info("All operations completed successfully!")


def do_action(auth, hostname, args):
    if args.debug:
        utils.DEBUG = 1
    with HostConnection(hostname, username=auth[0], password=auth[1]):
        create_svm(args)
        create_volume(args)


if __name__ == "__main__":
    main()
