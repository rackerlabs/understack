"""What every Cisco NX-OS interface shares."""

from ironic.common import exception
from oslo_utils import strutils

from ironic_understack.conf import CONF
from ironic_understack.utils import nxos_api

REQUIRED_PROPERTIES = {
    "nxos_address": "Address of the switch's management interface, "
    "used for NX-API. Required.",
}
OPTIONAL_PROPERTIES = {
    "nxos_username": "NX-API username. Defaults to [cisco_nxos] username; "
    "required if that is unset.",
    "nxos_password": "NX-API password. Defaults to [cisco_nxos] password; "
    "required if that is unset.",
    "nxos_verify_ca": "Either a Boolean value, a path to a CA_BUNDLE file or "
    "directory with certificates of trusted CAs. If set to True the driver "
    "will verify the host certificates; if False the driver will ignore "
    "verifying the SSL certificate. Defaults to [cisco_nxos] verify_ca, "
    "which is False. Optional.",
}


class CiscoNxosInterface:
    """Mixin for NX-OS interfaces: each reaches the switch over NX-API.

    Every setting is in driver_info under an ``nxos_`` prefix, named like the
    redfish driver's (``nxos_address`` alongside ``redfish_address``). The
    credentials and ``nxos_verify_ca`` fall back to the ``[cisco_nxos]``
    config group when unset.
    """

    def get_properties(self):
        return {**REQUIRED_PROPERTIES, **OPTIONAL_PROPERTIES}

    def validate(self, task):
        node = task.node
        missing = [k for k in REQUIRED_PROPERTIES if not node.driver_info.get(k)]
        missing += [
            f"nxos_{key}" for key in ("username", "password") if not _setting(node, key)
        ]
        if missing:
            raise exception.MissingParameterValue(
                f"Node {node.uuid} is missing driver_info {', '.join(missing)} "
                "and [cisco_nxos] has no default"
            )
        _verify_ca(node)


def _setting(node, key: str):
    """Return driver_info ``nxos_<key>``, else ``[cisco_nxos] <key>``."""
    value = node.driver_info.get(f"nxos_{key}")
    if value is None or value == "":
        return getattr(CONF.cisco_nxos, key)
    return value


def _verify_ca(node) -> bool | str:
    """Parse ``verify_ca`` the way the redfish driver parses its own."""
    value = _setting(node, "verify_ca")
    if isinstance(value, bool):
        return value
    if not isinstance(value, str) or not value:
        raise exception.InvalidParameterValue(
            f"Node {node.uuid}: nxos_verify_ca must be a Boolean or a path, "
            f"not {value!r}"
        )
    try:
        return strutils.bool_from_string(value, strict=True)
    except ValueError:
        return value  # a path to a CA bundle


def client(node) -> nxos_api.NxosClient:
    """Return an NX-API client for the switch the node describes."""
    return nxos_api.NxosClient(
        node.driver_info["nxos_address"],
        _setting(node, "username"),
        _setting(node, "password"),
        verify=_verify_ca(node),
    )
