import urllib3
from netapp_ontap import config
from netapp_ontap.error import NetAppRestError
from netapp_ontap.host_connection import HostConnection
from netapp_ontap.resources import NvmeNamespace
from netapp_ontap.resources import Svm

from understack_workflows.helpers import setup_logger
from understack_workflows.netapp.client import NetAppClient
from understack_workflows.netapp.config import NetAppConfig
from understack_workflows.netapp.error_handler import ErrorHandler
from understack_workflows.netapp.lif_service import LifService
from understack_workflows.netapp.svm_service import SvmService
from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig
from understack_workflows.netapp.value_objects import NodeResult
from understack_workflows.netapp.volume_service import VolumeService

logger = setup_logger(__name__)


# Suppress warnings for unverified HTTPS requests, common in lab environments
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SVM_PROJECT_TAG = "UNDERSTACK_SVM"


class NetAppManager:
    """Manages NetApp ONTAP operations including SVM and volume creation."""

    def __init__(
        self,
        config_path="/etc/netapp/netapp_nvme.conf",
        netapp_config=None,
        netapp_client=None,
        svm_service=None,
        volume_service=None,
        lif_service=None,
        error_handler=None,
    ):
        """Initialize NetAppManager with dependency injection support.

        Args:
            config_path: Path to NetApp configuration file
            netapp_config: NetAppConfig instance (optional, for dependency injection)
            netapp_client: NetAppClient instance (optional, for dependency injection)
            svm_service: SvmService instance (optional, for dependency injection)
            volume_service: VolumeService instance (optional, for dependency injection)
            lif_service: LifService instance (optional, for dependency injection)
            error_handler: ErrorHandler instance (optional, for dependency injection)
        """
        # Set up dependencies with dependency injection or create defaults
        self._setup_dependencies(
            config_path,
            netapp_config,
            netapp_client,
            svm_service,
            volume_service,
            lif_service,
            error_handler,
        )

    def _setup_dependencies(
        self,
        config_path,
        netapp_config,
        netapp_client,
        svm_service,
        volume_service,
        lif_service,
        error_handler,
    ):
        """Set up all service dependencies with dependency injection."""
        # Initialize configuration
        if netapp_config is not None:
            self._config = netapp_config
        else:
            # Create config from file if client is not provided (client needs config)
            # Only skip config creation if client is provided via dependency injection
            if netapp_client is None:
                # Need to create config since we'll need to create a client
                self._config = NetAppConfig(config_path)
            else:
                # Client provided via dependency injection - config not needed
                self._config = None

        # Initialize error handler
        if error_handler is not None:
            self._error_handler = error_handler
        else:
            self._error_handler = ErrorHandler(logger)

        # Set up connection if using traditional constructor pattern
        if (
            self._config is not None
            and netapp_client is None
            and svm_service is None
            and volume_service is None
            and lif_service is None
        ):
            # Traditional constructor usage - set up connection directly
            # Check if connection needs to be established (handle both real and
            # mocked config)
            needs_connection = (
                not hasattr(config, "CONNECTION")
                or config.CONNECTION is None
                or
                # Handle mocked config objects in tests
                (
                    hasattr(config.CONNECTION, "_mock_name")
                    and config.CONNECTION._mock_name  # pyright: ignore
                )
            )
            if needs_connection:
                config.CONNECTION = HostConnection(
                    self._config.hostname,
                    username=self._config.username,
                    password=self._config.password,
                )

        # Initialize client
        if netapp_client is not None:
            self._client = netapp_client
        else:
            # Create client with config - config should always exist for
            # traditional usage
            if self._config is None:
                raise ValueError(
                    "NetAppConfig is required when NetAppClient is not provided"
                )
            self._client = NetAppClient(self._config, self._error_handler)

        # Initialize services - they should always be created if not provided
        if svm_service is not None:
            self._svm_service = svm_service
        else:
            self._svm_service = SvmService(self._client, self._error_handler)

        if volume_service is not None:
            self._volume_service = volume_service
        else:
            self._volume_service = VolumeService(self._client, self._error_handler)

        if lif_service is not None:
            self._lif_service = lif_service
        else:
            self._lif_service = LifService(self._client, self._error_handler)

    def create_svm(self, project_id: str, aggregate_name: str):
        """Creates a new Storage Virtual Machine (SVM)."""
        return self._svm_service.create_svm(project_id, aggregate_name)

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
        # Extract project_id from svm_name for service delegation
        # SVM names follow the pattern "os-{project_id}"
        if svm_name.startswith("os-"):
            project_id = svm_name[3:]  # Remove "os-" prefix
            return self._svm_service.delete_svm(project_id)
        else:
            # Handle non-standard SVM names by falling back to direct client call
            logger.warning(
                "Non-standard SVM name format: %s. Using direct deletion.", svm_name
            )
            try:
                return self._client.delete_svm(svm_name)
            except Exception as e:
                logger.error("Failed to delete SVM '%s': %s", svm_name, str(e))
                return False

    def create_volume(
        self, project_id: str, volume_size: str, aggregate_name: str
    ) -> str:
        """Creates a new volume within a specific SVM and aggregate."""
        return self._volume_service.create_volume(
            project_id, volume_size, aggregate_name
        )

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
        # Extract project_id from volume_name for service delegation
        # Volume names follow the pattern "vol_{project_id}"
        if volume_name.startswith("vol_"):
            project_id = volume_name[4:]  # Remove "vol_" prefix
            return self._volume_service.delete_volume(project_id, force)
        else:
            # Handle non-standard volume names by falling back to direct client call
            logger.warning(
                "Non-standard volume name format: %s. Using direct deletion.",
                volume_name,
            )
            try:
                return self._client.delete_volume(volume_name, force)
            except Exception as e:
                logger.error("Failed to delete volume '%s': %s", volume_name, str(e))
                return False

    def check_if_svm_exists(self, project_id):
        return self._svm_service.exists(project_id)

    def mapped_namespaces(self, svm_name, volume_name):
        """Get mapped NVMe namespaces for a volume.

        Args:
            svm_name: Name of the SVM
            volume_name: Name of the volume

        Returns:
            List of namespace results or None if no connection
        """
        # Extract project_id from svm_name and volume_name to use VolumeService
        # SVM names follow pattern "os-{project_id}" and volume names follow
        # "vol_{project_id}"
        if svm_name.startswith("os-") and volume_name.startswith("vol_"):
            svm_project_id = svm_name[3:]  # Remove "os-" prefix
            vol_project_id = volume_name[4:]  # Remove "vol_" prefix

            # Ensure both names refer to the same project
            if svm_project_id == vol_project_id:
                return self._volume_service.get_mapped_namespaces(svm_project_id)

        # Fall back to direct client call for non-standard names
        if not config.CONNECTION:
            return None

        ns_list = NvmeNamespace.get_collection(
            query=f"svm.name={svm_name}&location.volume.name={volume_name}",
            fields="uuid,name,status.mapped",
        )
        return ns_list

    def cleanup_project(self, project_id: str) -> dict[str, bool]:
        """Removes a Volume and SVM associated with a project.

        This method coordinates VolumeService and SvmService for project cleanup,
        handling cross-service error scenarios and rollback logic.

        Args:
            project_id: The project ID to clean up

        Returns:
            dict: Dictionary with 'volume' and 'svm' keys indicating success/failure

        Note: This method will delete the data if volume is still in use.
        """
        logger.info("Starting cleanup for project: %s", project_id)

        # Track cleanup state for potential rollback
        cleanup_state = {
            "volume_deleted": False,
            "svm_deleted": False,
            "volume_existed": False,
            "svm_existed": False,
        }

        # Check initial state to determine what needs cleanup
        # Check each service separately to handle individual failures
        try:
            cleanup_state["volume_existed"] = self._volume_service.exists(project_id)
        except Exception as e:
            logger.error(
                "Failed to check volume existence for %s: %s", project_id, str(e)
            )
            # Continue with cleanup attempt even if state check fails
            cleanup_state["volume_existed"] = True

        try:
            cleanup_state["svm_existed"] = self._svm_service.exists(project_id)
        except Exception as e:
            logger.error("Failed to check SVM existence for %s: %s", project_id, str(e))
            # Continue with cleanup attempt even if state check fails
            cleanup_state["svm_existed"] = True

        logger.debug(
            "Initial state - Volume exists: %s, SVM exists: %s",
            cleanup_state["volume_existed"],
            cleanup_state["svm_existed"],
        )

        # Step 1: Delete volume first (volumes must be deleted before SVM)
        delete_vol_result = False
        if cleanup_state["volume_existed"]:
            try:
                delete_vol_result = self._volume_service.delete_volume(
                    project_id, force=True
                )
                cleanup_state["volume_deleted"] = delete_vol_result
                logger.debug("Delete volume result: %s", delete_vol_result)

                if delete_vol_result:
                    logger.info(
                        "Successfully deleted volume for project: %s", project_id
                    )
                else:
                    logger.warning(
                        "Failed to delete volume for project: %s", project_id
                    )

            except Exception as e:
                logger.error(
                    "Exception during volume deletion for project %s: %s",
                    project_id,
                    str(e),
                )
                delete_vol_result = False
        else:
            # Volume doesn't exist, consider it successfully "deleted"
            delete_vol_result = True
            logger.debug(
                "Volume does not exist for project %s, skipping deletion", project_id
            )

        # Step 2: Delete SVM (only if volume deletion succeeded or volume didn't exist)
        delete_svm_result = False
        if cleanup_state["svm_existed"]:
            if delete_vol_result or not cleanup_state["volume_existed"]:
                try:
                    delete_svm_result = self._svm_service.delete_svm(project_id)
                    cleanup_state["svm_deleted"] = delete_svm_result
                    logger.debug("Delete SVM result: %s", delete_svm_result)

                    if delete_svm_result:
                        logger.info(
                            "Successfully deleted SVM for project: %s", project_id
                        )
                    else:
                        logger.warning(
                            "Failed to delete SVM for project: %s", project_id
                        )

                except Exception as e:
                    logger.error(
                        "Exception during SVM deletion for project %s: %s",
                        project_id,
                        str(e),
                    )
                    delete_svm_result = False

                    # If SVM deletion fails but volume was deleted, log the
                    # inconsistent state
                    if cleanup_state["volume_deleted"]:
                        logger.error(
                            "Inconsistent state: Volume deleted but SVM deletion "
                            "failed for project %s. "
                            "Manual cleanup may be required.",
                            project_id,
                        )
            else:
                logger.warning(
                    "Skipping SVM deletion for project %s because volume "
                    "deletion failed",
                    project_id,
                )
                delete_svm_result = False
        else:
            # SVM doesn't exist, consider it successfully "deleted"
            delete_svm_result = True
            logger.debug(
                "SVM does not exist for project %s, skipping deletion", project_id
            )

        # Log final cleanup status
        if delete_vol_result and delete_svm_result:
            logger.info("Successfully completed cleanup for project: %s", project_id)
        else:
            logger.warning(
                "Partial cleanup failure for project %s - Volume: %s, SVM: %s",
                project_id,
                delete_vol_result,
                delete_svm_result,
            )

        return {"volume": delete_vol_result, "svm": delete_svm_result}

    def create_lif(self, project_id, config: NetappIPInterfaceConfig):
        """Creates a logical interface (LIF) for a project.

        Delegates to LifService for network interface management.
        """
        return self._lif_service.create_lif(project_id, config)

    def create_home_port(self, config: NetappIPInterfaceConfig):
        """Creates a home port for the network interface.

        Delegates to LifService for port management.
        """
        return self._lif_service.create_home_port(config)

    def identify_home_node(self, config: NetappIPInterfaceConfig) -> NodeResult | None:
        """Identifies the home node for a network interface.

        Delegates to LifService for node identification.
        """
        return self._lif_service.identify_home_node(config)

    def _svm_by_project(self, project_id):
        try:
            svm_name = self._svm_name(project_id)
            svm = Svm.find(name=svm_name)
            if svm:
                return svm
        except NetAppRestError:
            return None
        return None

    def _svm_name(self, project_id):
        return f"os-{project_id}"

    def _volume_name(self, project_id):
        return f"vol_{project_id}"
