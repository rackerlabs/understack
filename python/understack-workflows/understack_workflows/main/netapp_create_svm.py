import argparse
import configparser
import logging
import os

import openstack
import urllib3
from netapp_ontap import config
from netapp_ontap import utils
from netapp_ontap.error import NetAppRestError
from netapp_ontap.host_connection import HostConnection
from netapp_ontap.resources import Svm
from netapp_ontap.resources import Volume

from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


# Suppress warnings for unverified HTTPS requests, common in lab environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SVM_PROJECT_TAG = "UNDERSTACK_SVM"


class NetAppManager:
    """Manages NetApp ONTAP operations including SVM and volume creation."""

    def __init__(self, args):
        self.args = args
        netapp_ini = self.parse_ontap_config(args.config_file)
        config.CONNECTION = HostConnection(
            netapp_ini["hostname"],
            username=netapp_ini["username"],
            password=netapp_ini["password"],
        )

    def parse_ontap_config(self, config_path="/etc/netapp/config.ini"):
        """Reads ONTAP connection details from a specified INI configuration file."""
        if not os.path.exists(config_path):
            logger.error("Configuration file not found at %s", config_path)
            exit(1)

        ontap_parser = configparser.ConfigParser()
        ontap_parser.read(config_path)

        try:
            logger.debug(
                "Reading configuration from section [netapp_nvme] in %s", config_path
            )
            hostname = ontap_parser.get("netapp_nvme", "netapp_server_hostname")
            login = ontap_parser.get("netapp_nvme", "netapp_login")
            password = ontap_parser.get("netapp_nvme", "netapp_password")
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            logger.error(
                "Missing required configuration in %s . Details: %s", config_path, e
            )
            exit(1)

        return {"hostname": hostname, "username": login, "password": password}

    def create_svm(self, args):
        """Creates a new Storage Virtual Machine (SVM)."""
        name = self._svm_name()
        root_name = f"{name}_root"

        logger.info("Creating SVM: %s...", name)
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
            logger.info(
                "SVM '%s' created successfully with NVMe protocol allowed", svm.name
            )
        except NetAppRestError as e:
            logger.error("Error creating SVM: %s", e)
            exit(1)

    def create_volume(self, args):
        """Creates a new volume within a specific SVM and aggregate."""
        volume_name = self._volume_name()
        volume_size_str = args.volume_size
        logger.info(
            "Creating volume '%(vname)s' with size %(size)s on aggregate '%(agg)s'...",
            {"vname": volume_name, "size": volume_size_str, "agg": args.aggregate_name},
        )

        try:
            volume = Volume(
                name=volume_name,
                svm={"name": self._svm_name()},
                aggregates=[{"name": args.aggregate_name}],
                size=args.volume_size,
            )
            volume.post()
            volume.get()
            logger.info("Volume %s created.", volume_name)
        except NetAppRestError as e:
            logger.error("Error creating Volume: %s", e)
            exit(1)

    def _svm_name(self):
        return f"os-{self.args.project_id}"

    def _volume_name(self):
        return f"vol_{self.args.project_id}"


class KeystoneProject:
    def __init__(self):
        self.conn = None

    def connect(self):
        self.conn = openstack.connect()

    def project_tags(self, project_id):
        if not self.conn:
            self.connect()

        project = self.conn.identity.get_project(project_id)
        if hasattr(project, "tags"):
            return project.tags
        else:
            return []


def argument_parser():
    parser = argparse.ArgumentParser(
        description="NetApp ONTAP SVM and Volume Creator via REST API",
        prog=os.path.basename(__file__),
    )
    parser.add_argument(
        "--project_id", required=True, help="Keystone project ID to create SVM for"
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
    """Main function to orchestrate the SVM and volume creation process."""
    args = argument_parser().parse_args()
    if args.debug:
        utils.DEBUG = 1
        logger.setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

    logger.info("Starting ONTAP SVM and Volume creation workflow.")

    netapp_manager = NetAppManager(args)
    kp = KeystoneProject()

    do_action(args, netapp_manager, kp)
    logger.info("All operations completed successfully!")


def do_action(args, netapp_manager, kp):
    tags = kp.project_tags(args.project_id)
    logger.debug("Project %s has tags: %s", args.project_id, tags)
    if not SVM_PROJECT_TAG in tags:
        logger.info("The %s is missing, not creating SVM.", SVM_PROJECT_TAG)
        exit(0)

    netapp_manager.create_svm(args)
    netapp_manager.create_volume(args)


if __name__ == "__main__":
    main()
