"""Minimal client for the PAN-OS XML API.

Credentials come from the ``[netdev_panos]`` oslo.config group; see
:mod:`ironic_understack.utils.netdev_credentials`.
"""

# Responses are only ever parsed from the appliance being managed, and the
# stdlib expat parser does not resolve external entities.
import xml.etree.ElementTree as ET

import requests
from oslo_log import log

from ironic_understack.conf import CONF
from ironic_understack.utils import netdev_credentials

LOG = log.getLogger(__name__)

TIMEOUT = 30

# Passwords are tried in this order. An appliance that has been through initial
# setup takes the standard password, one part way through takes preconfig, and
# a factory-fresh one still takes the factory default.
PASSWORD_ORDER = (
    ("standard", "standard_password"),
    ("preconfig", "preconfig_password"),
    ("factory", "factory_password"),
)


class PanosApiError(Exception):
    """The PAN-OS API rejected a request or returned an unusable response."""


class PanosClient:
    def __init__(self, address: str, session: requests.Session | None = None):
        self.address = address
        self.url = f"https://{address}/api/"
        self.session = session or requests.Session()
        self.session.verify = CONF.netdev_panos.verify_ssl
        self.api_key: str | None = None

    def login(self) -> str:
        """Obtain an API key, trying each configured password in turn.

        :returns: the label of the password that was accepted.
        :raises PanosApiError: if no configured password is accepted.
        """
        creds = netdev_credentials.get_panos_credentials()
        tried = []
        for label, key in PASSWORD_ORDER:
            password = creds[key]
            if not password:
                continue
            tried.append(label)
            api_key = self._keygen(creds["username"], password)
            if api_key:
                self.api_key = api_key
                return label
            LOG.debug("PAN-OS %s rejected the %s password", self.address, label)

        if not tried:
            raise PanosApiError("no PAN-OS passwords are configured in [netdev_panos]")
        raise PanosApiError(f"rejected the {', '.join(tried)} password(s)")

    def _keygen(self, username: str, password: str) -> str | None:
        # POST so the password is never part of a URL that might be logged.
        resp = self.session.post(
            self.url,
            data={"type": "keygen", "user": username, "password": password},
            timeout=TIMEOUT,
        )
        if resp.status_code == 403:
            return None
        key = _parse(resp).findtext("./result/key")
        if not key:
            raise PanosApiError("keygen response did not contain a key")
        return key

    def op(self, cmd: str) -> ET.Element:
        """Run an operational command and return its ``<result>`` element."""
        if self.api_key is None:
            raise PanosApiError("not logged in")
        resp = self.session.post(
            self.url,
            data={"type": "op", "cmd": cmd},
            headers={"X-PAN-KEY": self.api_key},
            timeout=TIMEOUT,
        )
        result = _parse(resp).find("result")
        if result is None:
            raise PanosApiError(f"no result for {cmd}")
        return result

    def system_info(self) -> dict[str, str]:
        """Return ``show system info`` as a flat dict of field name to value."""
        system = self.op("<show><system><info></info></system></show>").find("system")
        if system is None:
            raise PanosApiError("show system info returned no system element")
        return {child.tag: (child.text or "").strip() for child in system}


def _parse(resp: requests.Response) -> ET.Element:
    try:
        root = ET.fromstring(resp.content)  # noqa: S314
    except ET.ParseError as e:
        raise PanosApiError(f"HTTP {resp.status_code}: response is not XML") from e
    if root.get("status") != "success":
        msg = " ".join(text.strip() for text in root.itertext() if text.strip())
        raise PanosApiError(f"HTTP {resp.status_code}: {msg or 'request failed'}")
    return root
