"""Network device credential management.

Credentials are loaded from oslo.config INI files.
The network-device-credentials secret is mounted via etcSources
and oslo.config automatically loads the network_devices.conf file.
"""

import logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)


def get_panos_credentials() -> dict[str, str | None]:
    """Get all PAN-OS credentials with 3-tier fallback.

    Credentials are read from the [panos] section of network_devices.conf
    which is automatically loaded by oslo.config via etcSources mount.

    Returns a dict with:
        - username: PAN-OS admin username
        - standard_password: Primary password (607061)
        - preconfig_password: Pre-config station password (607060)
        - factory_password: Factory default ('admin')
        - panorama_master_key: Panorama registration key (607341)

    Missing credentials will have None values.
    """
    try:
        # Oslo.config registers the [panos] group when network_devices.conf is loaded
        panos_conf = CONF.panos
        return {
            "username": getattr(panos_conf, "username", "admin"),
            "standard_password": getattr(panos_conf, "standard_password", None),
            "preconfig_password": getattr(panos_conf, "preconfig_password", None),
            "factory_password": getattr(panos_conf, "factory_password", "admin"),
            "panorama_master_key": getattr(panos_conf, "panorama_master_key", None),
        }
    except Exception as e:
        LOG.warning(
            "Failed to load PAN-OS credentials from oslo.config: %s. "
            "network-device-credentials secret may not be mounted.",
            e,
        )
        return {
            "username": "admin",
            "standard_password": None,
            "preconfig_password": None,
            "factory_password": "admin",
            "panorama_master_key": None,
        }


def get_f5_credentials() -> dict[str, dict[str, str | None]]:
    """Get all F5 credentials with 2-tier fallback for both accounts.

    F5 has two distinct local accounts:
    - 'root' for AOM interface (SSH to management interface)
    - 'admin' for UI/API access

    Both accounts use the same passwords from PasswordSafe.

    Returns a dict with:
        - root: dict with username, standard_password, preconfig_password
        - admin: dict with username, standard_password, preconfig_password

    Missing credentials will have None values.
    """
    try:
        f5_conf = CONF.f5
        return {
            "root": {
                "username": getattr(f5_conf, "root_username", "root"),
                "standard_password": getattr(f5_conf, "root_standard_password", None),
                "preconfig_password": getattr(f5_conf, "root_preconfig_password", None),
            },
            "admin": {
                "username": getattr(f5_conf, "admin_username", "admin"),
                "standard_password": getattr(f5_conf, "admin_standard_password", None),
                "preconfig_password": getattr(
                    f5_conf, "admin_preconfig_password", None
                ),
            },
        }
    except Exception as e:
        LOG.warning(
            "Failed to load F5 credentials from oslo.config: %s. "
            "network-device-credentials secret may not be mounted.",
            e,
        )
        return {
            "root": {
                "username": "root",
                "standard_password": None,
                "preconfig_password": None,
            },
            "admin": {
                "username": "admin",
                "standard_password": None,
                "preconfig_password": None,
            },
        }


def get_service_accounts() -> dict[str, dict[str, str | None]]:
    """Get shared service account credentials.

    These are automation/API accounts for device management,
    NOT per-device TACACS keys (those are fetched dynamically).

    Returns a dict with:
        - account_a: dict with username and password
        - account_b: dict with username and password

    Missing credentials will have None values.
    """
    try:
        svc_conf = CONF.service_accounts
        return {
            "account_a": {
                "username": getattr(svc_conf, "service_account_a_username", None),
                "password": getattr(svc_conf, "service_account_a_password", None),
            },
            "account_b": {
                "username": getattr(svc_conf, "service_account_b_username", None),
                "password": getattr(svc_conf, "service_account_b_password", None),
            },
        }
    except Exception as e:
        LOG.warning(
            "Failed to load service account credentials from oslo.config: %s. "
            "network-device-credentials secret may not be mounted.",
            e,
        )
        return {
            "account_a": {"username": None, "password": None},
            "account_b": {"username": None, "password": None},
        }
