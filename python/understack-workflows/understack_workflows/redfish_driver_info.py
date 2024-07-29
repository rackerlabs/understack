from dataclasses import dataclass


@dataclass
class RedfishDriverInfo:
    redfish_address: str
    """The URL address to the Redfish controller"""

    redfish_system_id: str | None = None
    """The canonical path to the ComputerSystem resource"""

    redfish_username: str | None = None
    """User account with admin/server-profile access"""

    redfish_password: str | None = None
    """User account password"""

    redfish_verify_ca: bool | str | None = None
    """If redfish_address has the https scheme, the
    driver will use a secure (TLS) connection when talking to the Redfish
    controller. By default (if this is not set or set to True), the driver will
    try to verify the host certificates. This can be set to the path of a
    certificate file or directory with trusted certificates that the driver
    will use for verification. To disable verifying TLS, set this to False.
    This is optional.
    """

    redfish_auth_type: str | None = None
    """ Redfish HTTP client authentication method. Can
    be “basic”, “session” or “auto”. The “auto” mode first tries “session” and
    falls back to “basic” if session authentication is not supported by the
    Redfish BMC. Default is set in ironic config as [redfish]auth_type.
    """
