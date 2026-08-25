"""Detect BMC password changes and dispatch to sync backends.

Listens for baremetal.node.update.end events and determines whether
a password field in driver_info has changed. When a change is detected
and the node is eligible, dispatches to the appropriate sync backend
based on the value of extra["password_sync"].

Supported backends (extensible):
  - "core"         → sync to Rackspace CORE via CTKAPI
  - "passwordsafe" → (future) sync to PasswordSafe
  - "1password"    → (future) sync to 1Password

A node is eligible when:
  - extra["password_sync"] is set to a recognized backend name
  - AND extra has a device identifier (core_id or external_cmdb_id)

Values of "false", "disabled", or absent skip sync entirely.

Change detection strategy:
  The oslo notification always includes the full (masked) driver_info —
  there is no "changed fields" metadata. To detect actual password
  changes we compare the current password (fetched via the Ironic API)
  against a hash stored in driver_internal_info after each successful
  sync.

  The hash is stored as:
    driver_internal_info["_uc_password_sync_hash"] = sha256(password)

  driver_internal_info is a freeform dict intended for internal
  bookkeeping — it is not validated by Ironic drivers and is safe
  for operator use with a namespaced key prefix.
"""

import hashlib
import logging
from abc import ABC
from abc import abstractmethod
from typing import Any

from openstack.connection import Connection
from pynautobot.core.api import Api as Nautobot

logger = logging.getLogger(__name__)

# Where we persist the last-synced password hash for change detection
_SYNC_HASH_KEY = "_uc_password_sync_hash"

# Extra keys for device identification
_CORE_ID_KEY = "core_id"
_EXTERNAL_CMDB_ID_KEY = "external_cmdb_id"

# Extra key that controls which backend to sync to
_PASSWORD_SYNC_KEY = "password_sync"

# Values that explicitly disable sync
_DISABLED_VALUES = {"false", "disabled", "none", ""}

# driver_info keys that hold passwords, ordered by priority
_PASSWORD_KEYS = ("redfish_password", "ipmi_password")


# --- Sync Backend Interface -------------------------------------------------


class PasswordSyncBackend(ABC):
    """Base class for password sync backends."""

    @abstractmethod
    def sync(
        self,
        device_id: str,
        password: str,
        node_uuid: str,
        node_name: str,
    ) -> bool:
        """Push the password to the external system.

        Args:
            device_id: External device identifier (core_id, etc.)
            password: The new BMC password to sync.
            node_uuid: Ironic node UUID for logging/correlation.
            node_name: Ironic node name for logging/correlation.

        Returns:
            True if the sync succeeded, False otherwise.
        """


class CoreBackend(PasswordSyncBackend):
    """Sync BMC password to Rackspace CORE via CTKAPI.

    Phase 1 (current): logging only.
    Phase 2 (future): actual CTKAPI call.
    """

    def sync(
        self,
        device_id: str,
        password: str,
        node_uuid: str,
        node_name: str,
    ) -> bool:
        # TODO(phase2): Implement CTKAPI password update
        # connector = Connector()
        # connector.login()
        # query = [{
        #     "class": "Computer.Password",
        #     "load_arg": {
        #         "device": int(device_id),
        #         "password_type": 8,
        #     },
        #     "method": "save",
        #     "keyword_args": {"password": password, "username": "root"},
        # }]
        # connector.query(query)
        logger.info(
            "[password_sync:core] Would sync password for node %s (%s) to CORE device %s",
            node_uuid,
            node_name,
            device_id,
        )
        return True


class PasswordSafeBackend(PasswordSyncBackend):
    """Sync BMC password to PasswordSafe. (Future)"""

    def sync(
        self,
        device_id: str,
        password: str,
        node_uuid: str,
        node_name: str,
    ) -> bool:
        logger.info(
            "[password_sync:passwordsafe] Would sync password"
            " for node %s (%s) to PasswordSafe device %s",
            node_uuid,
            node_name,
            device_id,
        )
        return False  # Not implemented


class OnePasswordBackend(PasswordSyncBackend):
    """Sync BMC password to 1Password. (Future)"""

    def sync(
        self,
        device_id: str,
        password: str,
        node_uuid: str,
        node_name: str,
    ) -> bool:
        logger.info(
            "[password_sync:1password] Would sync password for node %s (%s) to 1Password device %s",
            node_uuid,
            node_name,
            device_id,
        )
        return False  # Not implemented


# Registry of available backends
_BACKENDS: dict[str, PasswordSyncBackend] = {
    "core": CoreBackend(),
    "passwordsafe": PasswordSafeBackend(),
    "1password": OnePasswordBackend(),
}


# --- Helpers ----------------------------------------------------------------


def _extract_node_uuid(event_data: dict[str, Any]) -> str | None:
    """Extract node UUID from a node CRUD event payload."""
    payload = event_data.get("payload", {})
    if isinstance(payload, dict):
        ironic_data = payload.get("ironic_object.data", {})
        if isinstance(ironic_data, dict) and ironic_data.get("uuid"):
            return ironic_data["uuid"]
    return None


def _get_password_from_driver_info(
    driver_info: dict[str, Any],
) -> tuple[str | None, str | None]:
    """Find the first password value in driver_info.

    Returns (key_name, password_value) or (None, None).
    Checks well-known keys first, then falls back to any key
    ending in '_password'.
    """
    for key in _PASSWORD_KEYS:
        value = driver_info.get(key)
        if value:
            return key, value

    # Fallback: any key ending in _password
    for key, value in driver_info.items():
        if key.endswith("_password") and value:
            return key, value

    return None, None


def _hash_password(password: str) -> str:
    """Return a hex SHA-256 hash of the password."""
    return hashlib.sha256(password.encode()).hexdigest()


def _get_backend(extra: dict[str, Any]) -> PasswordSyncBackend | None:
    """Determine the sync backend from node extra.

    Returns None if sync is disabled or backend is unrecognized.
    """
    raw_value = str(extra.get(_PASSWORD_SYNC_KEY, "")).strip().lower()

    if not raw_value or raw_value in _DISABLED_VALUES:
        return None

    backend = _BACKENDS.get(raw_value)
    if backend is None:
        logger.warning(
            "[password_sync] Unrecognized backend '%s'. Available: %s",
            raw_value,
            list(_BACKENDS.keys()),
        )
    return backend


def _get_device_id(extra: dict[str, Any]) -> str | None:
    """Return the external device identifier, or None."""
    value = extra.get(_CORE_ID_KEY) or extra.get(_EXTERNAL_CMDB_ID_KEY)
    return str(value) if value else None


# --- Event Handler ----------------------------------------------------------


def handle_node_update(
    conn: Connection, _nautobot: Nautobot, event_data: dict[str, Any]
) -> int:
    """Handle baremetal.node.update.end for password change detection.

    Determines if the node's BMC password has changed and dispatches
    to the configured sync backend.
    """
    node_uuid = _extract_node_uuid(event_data)
    if not node_uuid:
        return 0

    # Fetch the full node (notification masks secrets)
    node = conn.baremetal.get_node(node_uuid)
    if node is None:
        logger.debug(
            "[password_sync] Node %s not found, skipping",
            node_uuid,
        )
        return 0

    extra = node.extra or {}

    # Determine backend; skip if disabled or absent
    backend = _get_backend(extra)
    if backend is None:
        return 0

    # Must have a device identifier to target
    device_id = _get_device_id(extra)
    if not device_id:
        logger.debug(
            "[password_sync] Node %s has password_sync enabled but no core_id or external_cmdb_id, skipping",
            node_uuid,
        )
        return 0

    # Extract password from driver_info
    driver_info = node.driver_info or {}
    password_key, password_value = _get_password_from_driver_info(driver_info)

    if not password_value:
        logger.debug(
            "[password_sync] Node %s has no password in driver_info",
            node_uuid,
        )
        return 0

    # Change detection: compare against stored hash
    driver_internal = node.driver_internal_info or {}
    stored_hash = driver_internal.get(_SYNC_HASH_KEY)
    current_hash = _hash_password(password_value)

    if stored_hash == current_hash:
        return 0

    # --- Password change detected ---
    node_name = node.name or node_uuid
    backend_name = str(extra.get(_PASSWORD_SYNC_KEY, "")).strip().lower()

    if stored_hash is None:
        logger.info(
            "[password_sync:%s] Node %s (%s): initial password detected (no prior hash). Device: %s, key: %s",
            backend_name,
            node_uuid,
            node_name,
            device_id,
            password_key,
        )
    else:
        logger.info(
            "[password_sync:%s] Node %s (%s): password CHANGED. Device: %s, key: %s",
            backend_name,
            node_uuid,
            node_name,
            device_id,
            password_key,
        )

    # Dispatch to backend
    success = backend.sync(
        device_id=device_id,
        password=password_value,
        node_uuid=node_uuid,
        node_name=node_name,
    )

    # Persist hash only after successful sync
    if success:
        # TODO(phase2): uncomment when backends perform real writes
        # conn.baremetal.update_node(
        #     node_uuid,
        #     [{"op": "add",
        #       "path": "/driver_internal_info/_uc_password_sync_hash",
        #       "value": current_hash}],
        # )
        logger.debug(
            "[password_sync:%s] Sync reported success for node %s",
            backend_name,
            node_uuid,
        )

    return 0
