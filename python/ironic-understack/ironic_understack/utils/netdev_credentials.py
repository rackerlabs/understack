"""Network device credential management.

Credentials are read from oslo.config groups loaded from network_devices.conf,
which is mounted via etcSources from the network-device-credentials-ini secret.
"""

import logging

from ironic_understack.conf import CONF

LOG = logging.getLogger(__name__)


def get_panos_credentials() -> dict[str, str | None]:
    """Get PAN-OS credentials. Missing values are None."""
    return {
        "username": CONF.netdev_panos.username,
        "standard_password": CONF.netdev_panos.standard_password,
        "preconfig_password": CONF.netdev_panos.preconfig_password,
        "factory_password": CONF.netdev_panos.factory_password,
        "panorama_master_key": CONF.netdev_panos.panorama_master_key,
    }


def get_f5_credentials() -> dict[str, dict[str, str | None]]:
    """Get F5 credentials for the root (AOM) and admin (UI/API) accounts.

    Missing values are None.
    """
    return {
        "root": {
            "username": CONF.netdev_f5.root_username,
            "standard_password": CONF.netdev_f5.root_standard_password,
            "preconfig_password": CONF.netdev_f5.root_preconfig_password,
        },
        "admin": {
            "username": CONF.netdev_f5.admin_username,
            "standard_password": CONF.netdev_f5.admin_standard_password,
            "preconfig_password": CONF.netdev_f5.admin_preconfig_password,
        },
    }


def get_service_accounts() -> dict[str, dict[str, str | None]]:
    """Get shared automation service account credentials. Missing values are None."""
    return {
        "account_a": {
            "username": CONF.netdev_common.service_account_a_username,
            "password": CONF.netdev_common.service_account_a_password,
        },
        "account_b": {
            "username": CONF.netdev_common.service_account_b_username,
            "password": CONF.netdev_common.service_account_b_password,
        },
    }
