import configparser
import os

import urllib3
from netapp_ontap import config
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

    def __init__(self, config_path="/etc/netapp/netapp_nvme.conf"):
        netapp_ini = self.parse_ontap_config(config_path)
        config.CONNECTION = HostConnection(
            netapp_ini["hostname"],
            username=netapp_ini["username"],
            password=netapp_ini["password"],
        )

    def parse_ontap_config(self, config_path):
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

    def create_svm(self, project_id: str, aggregate_name: str):
        """Creates a new Storage Virtual Machine (SVM)."""
        name = self._svm_name(project_id)
        root_name = f"{name}_root"

        logger.info("Creating SVM: %s...", name)
        try:
            svm = Svm(
                name=name,
                aggregates=[{"name": aggregate_name}],
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
            return name
        except NetAppRestError as e:
            logger.error("Error creating SVM: %s", e)
            exit(1)

    def create_volume(self, project_id: str, volume_size: str, aggregate_name: str):
        """Creates a new volume within a specific SVM and aggregate."""
        volume_name = self._volume_name(project_id)
        logger.info(
            "Creating volume '%(vname)s' with size %(size)s on aggregate '%(agg)s'...",
            {"vname": volume_name, "size": volume_size, "agg": aggregate_name},
        )

        try:
            volume = Volume(
                name=volume_name,
                svm={"name": self._svm_name(project_id)},
                aggregates=[{"name": aggregate_name}],
                size=volume_size,
            )
            volume.post()
            volume.get()
            logger.info("Volume %s created.", volume_name)
        except NetAppRestError as e:
            logger.error("Error creating Volume: %s", e)
            exit(1)

    def _svm_name(self, project_id):
        return f"os-{project_id}"

    def _volume_name(self, project_id):
        return f"vol_{project_id}"
