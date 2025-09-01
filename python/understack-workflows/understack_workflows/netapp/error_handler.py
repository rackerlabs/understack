"""Centralized error handling for NetApp Manager operations."""

import logging
from typing import Any

from netapp_ontap.error import NetAppRestError

from understack_workflows.netapp.exceptions import ConfigurationError
from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.exceptions import NetworkOperationError
from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError


class ErrorHandler:
    """Centralized error handling and logging for NetApp operations."""

    def __init__(self, logger: logging.Logger):
        """Initialize the error handler.

        Args:
            logger: Logger instance for error reporting
        """
        self._logger = logger

    def handle_netapp_error(
        self,
        error: NetAppRestError,
        operation: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Handle NetApp REST API errors and convert to domain-specific exceptions.

        Args:
            error: The NetApp REST error
            operation: Description of the operation that failed
            context: Additional context information

        Raises:
            NetAppManagerError: Appropriate domain-specific exception
        """
        context = context or {}
        error_message = f"NetApp {operation} failed: {error}"

        # Log the detailed error
        self._logger.error(
            "NetApp operation failed - Operation: %s, Error: %s, Context: %s",
            operation,
            str(error),
            context,
        )

        # Convert to domain-specific exceptions based on operation type
        operation_lower = operation.lower()

        if "svm" in operation_lower:
            svm_name = context.get("svm_name")
            raise SvmOperationError(
                error_message,
                svm_name=svm_name, # pyright: ignore
                context={**context, "netapp_error": str(error)},
            )
        elif "volume" in operation_lower:
            volume_name = context.get("volume_name")
            raise VolumeOperationError(
                error_message,
                volume_name=volume_name, # pyright: ignore
                context={**context, "netapp_error": str(error)},
            )
        elif any(
            term in operation_lower for term in ["lif", "interface", "port", "network"]
        ):
            interface_name = context.get("interface_name")
            raise NetworkOperationError(
                error_message,
                interface_name=interface_name, # pyright: ignore
                context={**context, "netapp_error": str(error)},
            )
        else:
            raise NetAppManagerError(
                error_message, context={**context, "netapp_error": str(error)}
            )

    def handle_config_error(
        self, error: Exception, config_path: str, context: dict[str, Any] | None = None
    ) -> None:
        """Handle configuration-related errors.

        Args:
            error: The configuration error
            config_path: Path to the configuration file
            context: Additional context information

        Raises:
            ConfigurationError: Configuration-specific exception
        """
        context = context or {}
        error_message = f"Configuration error with {config_path}: {error}"

        self._logger.error(
            "Configuration error - Path: %s, Error: %s, Context: %s",
            config_path,
            str(error),
            context,
        )

        raise ConfigurationError(
            error_message,
            config_path=config_path,
            context={**context, "original_error": str(error)},
        )

    def handle_operation_error(
        self, error: Exception, operation: str, context: dict[str, Any] | None = None
    ) -> None:
        """Handle general operation errors.

        Args:
            error: The operation error
            operation: Description of the operation that failed
            context: Additional context information

        Raises:
            NetAppManagerError: General NetApp manager exception
        """
        context = context or {}
        error_message = f"Operation '{operation}' failed: {error}"

        self._logger.error(
            "Operation failed - Operation: %s, Error: %s, Context: %s",
            operation,
            str(error),
            context,
        )

        raise NetAppManagerError(
            error_message, context={**context, "original_error": str(error)}
        )

    def log_warning(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Log a warning message with context.

        Args:
            message: Warning message
            context: Additional context information
        """
        if context:
            self._logger.warning("%s - Context: %s", message, context)
        else:
            self._logger.warning(message)

    def log_info(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Log an info message with context.

        Args:
            message: Info message
            context: Additional context information
        """
        if context:
            self._logger.info("%s - Context: %s", message, context)
        else:
            self._logger.info(message)

    def log_debug(self, message: str, context: dict[str, Any] | None = None) -> None:
        """Log a debug message with context.

        Args:
            message: Debug message
            context: Additional context information
        """
        if context:
            self._logger.debug("%s - Context: %s", message, context)
        else:
            self._logger.debug(message)
