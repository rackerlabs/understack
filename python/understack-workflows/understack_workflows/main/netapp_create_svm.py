import argparse
import configparser
import os

import openstack
import urllib3
from netapp_ontamp import config
from netapp_ontap import utils
from netapp_ontap.error import NetAppRestError
from netapp_ontap.host_connection import HostConnection
from netapp_ontap.resources import Svm, Volume
from understack_workflows.helpers import setup_logger

logger = setup_logger(__name__)


# Suppress warnings for unverified HTTPS requests, common in lab environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class NetAppManager:
    """Manages NetApp ONTAP operations including SVM and volume creation."""

    def __init__(self, args, logger):
        self.logger = logger
        self.args = args
        netapp_ini = self.parse_ontap_config(args.config_file)
        config.CONNECTION = HostConnection(
            netapp_ini["hostname"], username=netapp_ini["username"], password=netapp_ini["password"]
        )

    def parse_ontap_config(self, config_path="/etc/netapp/config.ini"):
        """
        Reads ONTAP connection details from a specified INI configuration file.
        """
        if not os.path.exists(config_path):
            self.logger.error(f"Configuration file not found at {config_path}")
            exit(1)

        ontap_parser = configparser.ConfigParser()
        ontap_parser.read(config_path)

        try:
            self.logger.debug(
                f"Reading configuration from section [netapp_nvme] in {config_path}"
            )
            hostname = ontap_parser.get("netapp_nvme", "netapp_server_hostname")
            login = ontap_parser.get("netapp_nvme", "netapp_login")
            password = ontap_parser.get("netapp_nvme", "netapp_password")
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            self.logger.error(
                f"Missing required configuration in {config_path}. Details: {e}"
            )
            exit(1)

        return {"hostname": hostname, "username": login, "password": password}

    def create_svm(self, args):
        """Creates a new Storage Virtual Machine (SVM)."""
        name = self._svm_name()
        root_name = f"{name}_root"

        self.logger.info(f"Creating SVM: {name}...")
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
            self.logger.info(
                f"SVM '{svm.name}' created successfully with NVMe protocol allowed"
            )
        except NetAppRestError as e:
            self.logger.error(f"Error creating SVM: {e}")
            exit(1)

    def create_volume(self, args):
        """Creates a new volume within a specific SVM and aggregate."""
        volume_name = self._volume_name()
        volume_size_str = args.volume_size
        self.logger.info(
            f"Creating volume '{volume_name}' with size {volume_size_str} on aggregate '{args.aggregate_name}'..."
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
            self.logger.info(f"Volume {volume_name} created.")
        except NetAppRestError as e:
            self.logger.error(f"Error creating Volume: {e}")
            exit(1)

    def _svm_name(self):
        return f"os-{self.args.project_id}"

    def _volume_name(self):
        return f"vol_{self.args.project_id}"


class KeystoneProject:
    def __init__(self, logger):
        self.logger = logger

    def connect(self):
        self.conn = openstack.connect()

    def project_tags(self, project_id):
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
    """
    Main function to orchestrate the SVM and volume creation process.
    """

    args = argument_parser().parse_args()
    logger.info("Starting ONTAP SVM and Volume creation workflow.")

    netapp_manager = NetAppManager(args, logger)

    do_action(args, netapp_manager)
    logger.info("All operations completed successfully!")


def do_action(args, netapp_manager):
    if args.debug:
        utils.DEBUG = 1

    netapp_manager.create_svm(args)
    netapp_manager.create_volume(args)


if __name__ == "__main__":
    main()
