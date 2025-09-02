"""Configuration management for NetApp Manager."""

import configparser
import os

from understack_workflows.netapp.exceptions import ConfigurationError


class NetAppConfig:
    """Handles NetApp configuration parsing and validation."""

    def __init__(self, config_path: str = "/etc/netapp/netapp_nvme.conf"):
        """Initialize NetApp configuration.

        Args:
            config_path: Path to the NetApp configuration file

        Raises:
            ConfigurationError: If configuration file is missing or invalid
        """
        self._config_path = config_path
        self._config_data = self._parse_config()
        self.validate()

    def _parse_config(self) -> dict[str, str]:
        """Parse the NetApp configuration file.

        Returns:
            Dictionary containing configuration values

        Raises:
            ConfigurationError: If file doesn't exist or has parsing errors
        """
        if not os.path.exists(self._config_path):
            raise ConfigurationError(
                f"Configuration file not found at {self._config_path}",
                config_path=self._config_path,
            )

        parser = configparser.ConfigParser()

        try:
            parser.read(self._config_path)
        except configparser.Error as e:
            raise ConfigurationError(
                f"Failed to parse configuration file: {e}",
                config_path=self._config_path,
                context={"parsing_error": str(e)},
            ) from e

        try:
            config_data = {
                "hostname": parser.get("netapp_nvme", "netapp_server_hostname"),
                "username": parser.get("netapp_nvme", "netapp_login"),
                "password": parser.get("netapp_nvme", "netapp_password"),
            }

            # Optional netapp_nic_slot_prefix with default value
            try:
                config_data["netapp_nic_slot_prefix"] = parser.get(
                    "netapp_nvme", "netapp_nic_slot_prefix"
                )
            except (configparser.NoSectionError, configparser.NoOptionError):
                config_data["netapp_nic_slot_prefix"] = "e4"

            return config_data
        except (configparser.NoSectionError, configparser.NoOptionError) as e:
            raise ConfigurationError(
                f"Missing required configuration in {self._config_path}: {e}",
                config_path=self._config_path,
                context={"missing_config": str(e)},
            ) from e

    def validate(self) -> None:
        """Validate that all required configuration values are present and valid.

        Raises:
            ConfigurationError: If any required configuration is missing or invalid
        """
        required_fields = ["hostname", "username", "password"]
        missing_fields = []
        empty_fields = []

        for field in required_fields:
            if field not in self._config_data:
                missing_fields.append(field)
            elif not self._config_data[field].strip():
                empty_fields.append(field)

        if missing_fields or empty_fields:
            error_parts = []
            if missing_fields:
                error_parts.append(f"Missing fields: {', '.join(missing_fields)}")
            if empty_fields:
                error_parts.append(f"Empty fields: {', '.join(empty_fields)}")

            raise ConfigurationError(
                f"Configuration validation failed: {'; '.join(error_parts)}",
                config_path=self._config_path,
                context={
                    "missing_fields": missing_fields,
                    "empty_fields": empty_fields,
                },
            )

    @property
    def hostname(self) -> str:
        """Get the NetApp server hostname."""
        return self._config_data["hostname"]

    @property
    def username(self) -> str:
        """Get the NetApp login username."""
        return self._config_data["username"]

    @property
    def password(self) -> str:
        """Get the NetApp login password."""
        return self._config_data["password"]

    @property
    def netapp_nic_slot_prefix(self) -> str:
        """Get the NetApp NIC slot prefix."""
        return self._config_data["netapp_nic_slot_prefix"]

    @property
    def config_path(self) -> str:
        """Get the configuration file path."""
        return self._config_path
