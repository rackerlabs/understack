"""Custom exception hierarchy for NetApp Manager operations."""
# pyright: reportArgumentType=false


class NetAppManagerError(Exception):
    """Base exception for NetApp Manager operations."""

    def __init__(self, message: str, context: dict = None):
        super().__init__(message)
        self.message = message
        self.context = context or {}


class ConfigurationError(NetAppManagerError):
    """Configuration-related errors."""

    def __init__(self, message: str, config_path: str = None, context: dict = None):
        super().__init__(message, context)
        self.config_path = config_path


class SvmOperationError(NetAppManagerError):
    """SVM operation errors."""

    def __init__(self, message: str, svm_name: str = None, context: dict = None):
        super().__init__(message, context)
        self.svm_name = svm_name


class VolumeOperationError(NetAppManagerError):
    """Volume operation errors."""

    def __init__(self, message: str, volume_name: str = None, context: dict = None):
        super().__init__(message, context)
        self.volume_name = volume_name


class NetworkOperationError(NetAppManagerError):
    """Network interface operation errors."""

    def __init__(self, message: str, interface_name: str = None, context: dict = None):
        super().__init__(message, context)
        self.interface_name = interface_name
