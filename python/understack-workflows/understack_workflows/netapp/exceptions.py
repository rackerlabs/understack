"""Custom exception hierarchy for NetApp Manager operations."""


class NetAppManagerError(Exception):
    """Base exception for NetApp Manager operations."""

    def __init__(self, message: str, context: dict | None = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}

    def __str__(self) -> str:
        """Render the base message plus any structured context."""
        if not self.context:
            return self.message
        return f"{self.message} | context={self.context}"


class ConfigurationError(NetAppManagerError):
    """Configuration-related errors."""

    def __init__(
        self,
        message: str,
        config_path: str | None = None,
        context: dict | None = None,
    ):
        super().__init__(message, context)
        self.config_path = config_path


class SvmOperationError(NetAppManagerError):
    """SVM operation errors."""

    def __init__(
        self,
        message: str,
        svm_name: str | None = None,
        context: dict | None = None,
    ):
        super().__init__(message, context)
        self.svm_name = svm_name


class SvmNotFoundError(SvmOperationError):
    """Raised when an expected SVM does not exist."""


class VolumeOperationError(NetAppManagerError):
    """Volume operation errors."""

    def __init__(
        self,
        message: str,
        volume_name: str | None = None,
        context: dict | None = None,
    ):
        super().__init__(message, context)
        self.volume_name = volume_name


class NetworkOperationError(NetAppManagerError):
    """Network interface operation errors."""

    def __init__(
        self,
        message: str,
        interface_name: str | None = None,
        context: dict | None = None,
    ):
        super().__init__(message, context)
        self.interface_name = interface_name


class HomeNodeNotFoundError(NetworkOperationError):
    """Raised when a matching home node cannot be identified."""
