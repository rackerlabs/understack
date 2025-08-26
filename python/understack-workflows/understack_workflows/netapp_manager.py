import configparser
import os

import urllib3
from netapp_ontap import config
from netapp_ontap.error import NetAppRestError
from netapp_ontap.host_connection import HostConnection
from netapp_ontap.resources import NvmeNamespace
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
            return svm.name
        except NetAppRestError as e:
            logger.error("Error creating SVM: %s", e)
            exit(1)

    def delete_svm(self, svm_name: str) -> bool:
        """Deletes a Storage Virtual Machine (SVM) based on its name.

        Args:
            svm_name (str): The name of the SVM to delete

        Returns:
            bool: True if deleted successfully, False otherwise

        Note:
            All non-root volumes, NVMe namespaces, and other dependencies
            must be deleted prior to deleting the SVM.
        """
        try:
            # Find the SVM by name
            svm = Svm()
            svm.get(name=svm_name)
            logger.info("Found SVM '%s' with UUID %s", svm_name, svm.uuid)
            svm.delete()
            logger.info("SVM '%s' deletion initiated successfully", svm_name)
            return True

        except Exception as e:
            logger.error("Failed to delete SVM '%s': %s", svm_name, str(e))
            return False

    def create_volume(
        self, project_id: str, volume_size: str, aggregate_name: str
    ) -> str:
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
            return volume_name
        except NetAppRestError as e:
            logger.error("Error creating Volume: %s", e)
            exit(1)

    def delete_volume(self, volume_name: str, force: bool = False) -> bool:
        """Deletes a volume based on volume name.

        Args:
            volume_name (str): The name of the volume to delete
            force (bool): If True, attempts to delete even if volume has dependencies

        Returns:
            bool: True if deleted successfully, False otherwise

        Raises:
            Exception: If volume not found or deletion fails
        """
        try:
            vol = Volume()
            vol.get(name=volume_name)

            logger.info("Found volume '%s'", volume_name)

            # Check if volume is online and has data
            if hasattr(vol, "state") and vol.state == "online":
                logger.warning("Volume '%s' is online", volume_name)

            if force:
                vol.delete(allow_delete_while_mapped=True)
            else:
                vol.delete()

            logger.info("Volume '%s' deletion initiated successfully", volume_name)
            return True

        except Exception as e:
            logger.error("Failed to delete volume '%s': %s", volume_name, str(e))
            return False

    def check_if_svm_exists(self, project_id):
        svm_name = self._svm_name(project_id)

        try:
            if Svm.find(name=svm_name):
                return True
        except NetAppRestError:
            return False

    def mapped_namespaces(self, svm_name, volume_name):
        if not config.CONNECTION:
            return

        ns_list = NvmeNamespace.get_collection(
            query=f"svm.name={svm_name}&location.volume.name={volume_name}",
            fields="uuid,name,status.mapped",
        )
        return ns_list

    def cleanup_project(self, project_id: str) -> dict[str, bool]:
        """Removes a Volume and SVM associated with a project.

        Note: This method will delete the data if volume is still in use.
        """
        svm_name = self._svm_name(project_id)
        vol_name = self._volume_name(project_id)
        delete_vol_result = self.delete_volume(vol_name)
        logger.debug("Delete volume result: %s", delete_vol_result)

        delete_svm_result = self.delete_svm(svm_name)
        logger.debug("Delete SVM result: %s", delete_svm_result)

        return {"volume": delete_vol_result, "svm": delete_svm_result}

    def _svm_name(self, project_id):
        return f"os-{project_id}"

    def _volume_name(self, project_id):
        return f"vol_{project_id}"
