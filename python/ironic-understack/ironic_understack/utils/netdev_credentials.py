"""Network device credential management.

Credentials are loaded from K8s secret mounts via oslo.config.
The network-device-credentials secret is mounted into Ironic pods
and read from a configurable directory path.
"""

import logging
from pathlib import Path

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)


def get_credential(key: str) -> str | None:
    """Read a credential from the network-device-credentials secret mount.

    Args:
        key: The credential key name (e.g., 'panos_standard_password')

    Returns:
        The credential value as a string, or None if not found or not mounted.

    Example:
        >>> password = get_credential('panos_standard_password')
        >>> username = get_credential('panos_username')
    """
    creds_dir = Path(CONF.ironic_understack.network_device_credentials_dir)
    cred_file = creds_dir / key

    if not creds_dir.exists():
        LOG.debug(
            "Network device credentials directory %s does not exist "
            "(secret not mounted or optional mount disabled)",
            creds_dir,
        )
        return None

    if not cred_file.exists():
        LOG.warning("Credential key '%s' not found in %s", key, creds_dir)
        return None

    try:
        return cred_file.read_text().strip()
    except Exception as e:
        LOG.error("Failed to read credential '%s': %s", key, e)
        return None


def get_panos_credentials() -> dict[str, str | None]:
    """Get all PAN-OS credentials with 3-tier fallback.

    Returns a dict with:
        - username: PAN-OS admin username
        - standard_password: Primary password (607061)
        - preconfig_password: Pre-config station password (607060)
        - factory_password: Factory default ('admin')
        - panorama_master_key: Panorama registration key (607341)

    Missing credentials will have None values.
    """
    return {
        "username": get_credential("panos_username") or "admin",
        "standard_password": get_credential("panos_standard_password"),
        "preconfig_password": get_credential("panos_preconfig_password"),
        "factory_password": get_credential("panos_factory_password") or "admin",
        "panorama_master_key": get_credential("panorama_master_key"),
    }
