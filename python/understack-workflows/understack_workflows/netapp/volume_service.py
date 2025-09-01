"""Volume service layer for NetApp Manager.

This module provides business logic for volume operations,
including naming conventions, lifecycle management, and namespace queries.
"""

import logging

from understack_workflows.netapp.client import NetAppClientInterface
from understack_workflows.netapp.error_handler import ErrorHandler
from understack_workflows.netapp.value_objects import NamespaceResult
from understack_workflows.netapp.value_objects import NamespaceSpec
from understack_workflows.netapp.value_objects import VolumeSpec


class VolumeService:
    """Service for managing volume operations with business logic."""

    def __init__(self, client: NetAppClientInterface, error_handler: ErrorHandler):
        """Initialize the volume service.

        Args:
            client: NetApp client for low-level operations
            error_handler: Error handler for centralized error management
        """
        self._client = client
        self._error_handler = error_handler
        self._logger = logging.getLogger(__name__)

    def create_volume(self, project_id: str, size: str, aggregate_name: str) -> str:  # pyright: ignore
        """Create a volume for a project with business naming conventions.

        Args:
            project_id: The project identifier
            size: Size of the volume (e.g., "1TB", "500GB")
            aggregate_name: Name of the aggregate to use for the volume

        Returns:
            str: The name of the created volume

        Raises:
            VolumeOperationError: If volume creation fails
        """
        volume_name = self.get_volume_name(project_id)
        svm_name = self._get_svm_name(project_id)

        # Create volume specification with business rules
        volume_spec = VolumeSpec(
            name=volume_name,
            svm_name=svm_name,
            aggregate_name=aggregate_name,
            size=size,
        )

        try:
            self._error_handler.log_info(
                "Creating volume for project %s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                    "size": size,
                    "aggregate": aggregate_name,
                },
            )

            result = self._client.create_volume(volume_spec)

            self._error_handler.log_info(
                "Volume created successfully for project %s",
                {
                    "project_id": project_id,
                    "volume_name": result.name,
                    "uuid": result.uuid,
                    "size": result.size,
                    "state": result.state,
                },
            )

            return result.name

        except Exception as e:
            self._error_handler.handle_operation_error(
                e,
                f"Volume creation for project {project_id}",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                    "size": size,
                    "aggregate_name": aggregate_name,
                },
            )

    def delete_volume(self, project_id: str, force: bool = False) -> bool:
        """Delete a volume for a project.

        Args:
            project_id: The project identifier
            force: If True, delete even if volume has dependencies

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        volume_name = self.get_volume_name(project_id)

        try:
            self._error_handler.log_info(
                "Deleting volume for project %s",
                {"project_id": project_id, "volume_name": volume_name, "force": force},
            )

            success = self._client.delete_volume(volume_name, force)

            if success:
                self._error_handler.log_info(
                    "Volume deleted successfully for project %s",
                    {"project_id": project_id, "volume_name": volume_name},
                )
            else:
                self._error_handler.log_warning(
                    "Volume deletion failed for project %s",
                    {"project_id": project_id, "volume_name": volume_name},
                )

            return success

        except Exception as e:
            self._error_handler.log_warning(
                "Error during volume deletion for project %s: %s",
                {"project_id": project_id, "volume_name": volume_name, "error": str(e)},
            )
            return False

    def get_volume_name(self, project_id: str) -> str:
        """Generate volume name using business naming conventions.

        Args:
            project_id: The project identifier

        Returns:
            str: The volume name following the convention 'vol_{project_id}'
        """
        return f"vol_{project_id}"

    def exists(self, project_id: str) -> bool:
        """Check if a volume exists for a project.

        Args:
            project_id: The project identifier

        Returns:
            bool: True if the volume exists, False otherwise
        """
        volume_name = self.get_volume_name(project_id)
        svm_name = self._get_svm_name(project_id)

        try:
            self._error_handler.log_debug(
                "Checking if volume exists for project %s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                },
            )

            volume_result = self._client.find_volume(volume_name, svm_name)
            exists = volume_result is not None

            self._error_handler.log_debug(
                "Volume existence check for project %s: %s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "exists": exists,
                },
            )

            return exists

        except Exception as e:
            self._error_handler.log_warning(
                "Error checking volume existence for project %s: %s",
                {"project_id": project_id, "volume_name": volume_name, "error": str(e)},
            )
            # Return False on error to avoid blocking cleanup operations
            return False

    def get_mapped_namespaces(self, project_id: str) -> list[NamespaceResult]:
        """Get mapped NVMe namespaces for a project's volume.

        Args:
            project_id: The project identifier

        Returns:
            List[NamespaceResult]: List of mapped namespaces for the project's volume
        """
        volume_name = self.get_volume_name(project_id)
        svm_name = self._get_svm_name(project_id)

        try:
            self._error_handler.log_debug(
                "Querying mapped namespaces for project %s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                },
            )

            namespace_spec = NamespaceSpec(svm_name=svm_name, volume_name=volume_name)

            namespaces = self._client.get_namespaces(namespace_spec)

            self._error_handler.log_info(
                "Retrieved %d namespaces for project %s",
                {
                    "project_id": project_id,
                    "namespace_count": len(namespaces),
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                },
            )

            return namespaces

        except Exception as e:
            self._error_handler.log_warning(
                "Error retrieving namespaces for project %s: %s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                    "error": str(e),
                },
            )
            return []

    def _get_svm_name(self, project_id: str) -> str:
        """Generate SVM name using business naming conventions.

        This is a private method that follows the same naming convention
        as the SvmService to ensure consistency.

        Args:
            project_id: The project identifier

        Returns:
            str: The SVM name following the convention 'os-{project_id}'
        """
        return f"os-{project_id}"
