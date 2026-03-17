"""Volume service layer for NetApp Manager.

This module provides business logic for volume operations,
including naming conventions, lifecycle management, and namespace queries.
"""

import logging

from understack_workflows.netapp.client import NetAppClientInterface
from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.exceptions import VolumeOperationError
from understack_workflows.netapp.value_objects import NamespaceResult
from understack_workflows.netapp.value_objects import NamespaceSpec
from understack_workflows.netapp.value_objects import VolumeSpec

logger = logging.getLogger(__name__)


class VolumeService:
    """Service for managing volume operations with business logic."""

    def __init__(self, client: NetAppClientInterface):
        """Initialize the volume service.

        Args:
            client: NetApp client for low-level operations
        """
        self._client = client

    def create_volume(
        self, project_id: str, volume_type_id: str, size: str, aggregate_name: str
    ) -> str:  # pyright: ignore
        """Create a volume for a project with business naming conventions.

        Args:
            project_id: The project identifier
            volume_type_id: The volume type identifier used to name the volume
            size: Size of the volume (e.g., "1TB", "500GB")
            aggregate_name: Name of the aggregate to use for the volume

        Returns:
            str: The name of the created volume

        Raises:
            VolumeOperationError: If volume creation fails
        """
        volume_name = self.get_volume_name(volume_type_id)
        svm_name = self._get_svm_name(project_id)

        # Create volume specification with business rules
        volume_spec = VolumeSpec(
            name=volume_name,
            svm_name=svm_name,
            aggregate_name=aggregate_name,
            size=size,
        )

        try:
            logger.info(
                "Creating volume for project %(project_id)s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                    "size": size,
                    "aggregate": aggregate_name,
                },
            )

            result = self._client.create_volume(volume_spec)

            logger.info(
                "Volume created successfully for project %(project_id)s",
                {
                    "project_id": project_id,
                    "volume_name": result.name,
                    "uuid": result.uuid,
                    "size": result.size,
                    "state": result.state,
                },
            )

            return result.name

        except NetAppManagerError:
            raise
        except Exception as e:
            raise VolumeOperationError(
                f"Operation 'Volume creation for project {project_id}' failed: {e}",
                volume_name=volume_name,
                context={
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                    "size": size,
                    "aggregate_name": aggregate_name,
                },
            ) from e

    def delete_volume(self, volume_type_id: str, force: bool = False) -> bool:
        """Delete a volume by volume_type_id.

        Args:
            volume_type_id: The volume type identifier used to derive the volume
                name. Can also be a project_id for backwards compatibility.
            force: If True, delete even if volume has dependencies

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        volume_name = self.get_volume_name(volume_type_id)

        try:
            logger.info(
                "Deleting volume %(volume_name)s",
                {
                    "volume_type_id": volume_type_id,
                    "volume_name": volume_name,
                    "force": force,
                },
            )

            success = self._client.delete_volume(volume_name, force)

            if success:
                logger.info(
                    "Volume deleted successfully %(volume_name)s",
                    {"volume_type_id": volume_type_id, "volume_name": volume_name},
                )
            else:
                logger.warning(
                    "Volume deletion failed %(volume_name)s",
                    {"volume_type_id": volume_type_id, "volume_name": volume_name},
                )

            return success

        except Exception as e:
            logger.warning(
                "Error during volume deletion %(volume_name)s: %(error)s",
                {
                    "volume_type_id": volume_type_id,
                    "volume_name": volume_name,
                    "error": str(e),
                },
            )
            return False

    def get_volume_name(self, volume_type_id: str) -> str:
        """Generate volume name using business naming conventions.

        Args:
            volume_type_id: The volume type identifier. Can also be a
                project_id for backwards compatibility.

        Returns:
            str: The volume name following the convention 'vol_{volume_type_id}'
        """
        return f"vol_{volume_type_id.replace('-', '')}"

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
            logger.debug(
                "Checking if volume exists for project %(project_id)s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                },
            )

            volume_result = self._client.find_volume(volume_name, svm_name)
            exists = volume_result is not None

            logger.debug(
                "Volume existence check for project %(project_id)s: %(exists)s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "exists": exists,
                },
            )

            return exists

        except Exception as e:
            logger.warning(
                "Error checking volume existence for project %(project_id)s: %(error)s",
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
            logger.debug(
                "Querying mapped namespaces for project %(project_id)s",
                {
                    "project_id": project_id,
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                },
            )

            namespace_spec = NamespaceSpec(svm_name=svm_name, volume_name=volume_name)

            namespaces = self._client.get_namespaces(namespace_spec)

            logger.info(
                "Retrieved %(namespace_count)d namespaces for project %(project_id)s",
                {
                    "project_id": project_id,
                    "namespace_count": len(namespaces),
                    "volume_name": volume_name,
                    "svm_name": svm_name,
                },
            )

            return namespaces

        except Exception as e:
            logger.warning(
                "Error retrieving namespaces for project %(project_id)s: %(error)s",
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
