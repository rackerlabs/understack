"""SVM service layer for NetApp Manager.

This module provides business logic for Storage Virtual Machine (SVM) operations,
including naming conventions, lifecycle management, and business rules.
"""

import logging

from understack_workflows.netapp.client import NetAppClientInterface
from understack_workflows.netapp.error_handler import ErrorHandler
from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.value_objects import SvmResult
from understack_workflows.netapp.value_objects import SvmSpec


class SvmService:
    """Service for managing Storage Virtual Machine (SVM) operations."""

    def __init__(self, client: NetAppClientInterface, error_handler: ErrorHandler):
        """Initialize the SVM service.

        Args:
            client: NetApp client for low-level operations
            error_handler: Error handler for centralized error management
        """
        self._client = client
        self._error_handler = error_handler
        self._logger = logging.getLogger(__name__)

    def create_svm(self, project_id: str, aggregate_name: str) -> str:  # pyright: ignore
        """Create an SVM for a project with business naming conventions.

        Args:
            project_id: The project identifier
            aggregate_name: Name of the aggregate to use for the SVM

        Returns:
            str: The name of the created SVM

        Raises:
            SvmOperationError: If SVM creation fails
        """
        svm_name = self.get_svm_name(project_id)

        # Check if SVM already exists
        if self.exists(project_id):
            self._error_handler.log_warning(
                "SVM already exists for project %s",
                {"project_id": project_id, "svm_name": svm_name},
            )
            raise SvmOperationError(
                f"SVM '{svm_name}' already exists for project '{project_id}'",
                svm_name=svm_name,
                context={"project_id": project_id, "aggregate_name": aggregate_name},
            )

        # Create SVM specification with business rules
        svm_spec = SvmSpec(
            name=svm_name,
            aggregate_name=aggregate_name,
            language="c.utf_8",
            allowed_protocols=["nvme"],
        )

        try:
            self._error_handler.log_info(
                "Creating SVM for project %s",
                {
                    "project_id": project_id,
                    "svm_name": svm_name,
                    "aggregate": aggregate_name,
                },
            )

            result = self._client.create_svm(svm_spec)

            self._error_handler.log_info(
                "SVM created successfully for project %s",
                {
                    "project_id": project_id,
                    "svm_name": result.name,
                    "uuid": result.uuid,
                    "state": result.state,
                },
            )

            return result.name

        except Exception as e:
            self._error_handler.handle_operation_error(
                e,
                f"SVM creation for project {project_id}",
                {
                    "project_id": project_id,
                    "svm_name": svm_name,
                    "aggregate_name": aggregate_name,
                },
            )

    def delete_svm(self, project_id: str) -> bool:
        """Delete an SVM for a project.

        Args:
            project_id: The project identifier

        Returns:
            bool: True if deletion was successful, False otherwise

        Note:
            All non-root volumes, NVMe namespaces, and other dependencies
            must be deleted prior to deleting the SVM.
        """
        svm_name = self.get_svm_name(project_id)

        try:
            self._error_handler.log_info(
                "Deleting SVM for project %s",
                {"project_id": project_id, "svm_name": svm_name},
            )

            success = self._client.delete_svm(svm_name)

            if success:
                self._error_handler.log_info(
                    "SVM deleted successfully for project %s",
                    {"project_id": project_id, "svm_name": svm_name},
                )
            else:
                self._error_handler.log_warning(
                    "SVM deletion failed for project %s",
                    {"project_id": project_id, "svm_name": svm_name},
                )

            return success

        except Exception as e:
            self._error_handler.log_warning(
                "Error during SVM deletion for project %s: %s",
                {"project_id": project_id, "svm_name": svm_name, "error": str(e)},
            )
            return False

    def exists(self, project_id: str) -> bool:
        """Check if an SVM exists for a project.

        Args:
            project_id: The project identifier

        Returns:
            bool: True if SVM exists, False otherwise
        """
        svm_name = self.get_svm_name(project_id)

        try:
            result = self._client.find_svm(svm_name)
            exists = result is not None

            self._error_handler.log_debug(
                "SVM existence check for project %s: %s",
                {"project_id": project_id, "svm_name": svm_name, "exists": exists},
            )

            return exists

        except Exception as e:
            self._error_handler.log_warning(
                "Error checking SVM existence for project %s: %s",
                {"project_id": project_id, "svm_name": svm_name, "error": str(e)},
            )
            return False

    def get_svm_name(self, project_id: str) -> str:
        """Generate SVM name using business naming conventions.

        Args:
            project_id: The project identifier

        Returns:
            str: The SVM name following the convention 'os-{project_id}'
        """
        return f"os-{project_id}"

    def get_svm_result(self, project_id: str) -> SvmResult | None:
        """Get SVM result for a project if it exists.

        Args:
            project_id: The project identifier

        Returns:
            Optional[SvmResult]: SVM result if found, None otherwise
        """
        svm_name = self.get_svm_name(project_id)

        try:
            return self._client.find_svm(svm_name)
        except Exception as e:
            self._error_handler.log_warning(
                "Error retrieving SVM for project %s: %s",
                {"project_id": project_id, "svm_name": svm_name, "error": str(e)},
            )
            return None
