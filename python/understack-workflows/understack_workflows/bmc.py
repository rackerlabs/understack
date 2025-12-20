# pylint: disable=E1131,C0103

import logging
import os
from dataclasses import dataclass

import requests
import urllib3
from sushy import Sushy

from understack_workflows.bmc_password_standard import standard_password
from understack_workflows.helpers import credential

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore
logging.getLogger("urllib3").setLevel(logging.WARNING)

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json; charset=utf-8",
}


class RedfishRequestError(Exception):
    """Handle Exceptions from Redfish handler."""


@dataclass
class Bmc:
    """Represent DRAC/iLo and know how to perform low-level query on it."""

    def __init__(
        self, ip_address: str, password: str | None = None, username: str = "root"
    ) -> None:
        """Initialize BMC data class."""
        self.ip_address = ip_address
        self.username = username
        self.password = password if password else ""
        self._system_path: str | None = None
        self._manager_path: str | None = None

    @property
    def system_path(self) -> str:
        """Read System path from BMC."""
        self._system_path = self._system_path or self.get_system_path()
        return self._system_path

    @property
    def manager_path(self) -> str:
        """Read Manager path from BMC."""
        self._manager_path = self._manager_path or self.get_manager_path()
        return self._manager_path

    def __str__(self):
        """Stringify without password being printed."""
        return f"BMC {self.url()}"

    def url(self):
        """Return base redfish URL."""
        return f"https://{self.ip_address}"

    def get_system_path(self):
        """Get System Path."""
        _result = self.redfish_request("/redfish/v1/Systems/")
        return _result["Members"][0]["@odata.id"].rstrip("/")

    def get_manager_path(self):
        """Get Manager Path."""
        _result = self.redfish_request("/redfish/v1/Managers/")
        return _result["Members"][0]["@odata.id"].rstrip("/")

    def redfish_request(
        self,
        path: str,
        method: str = "GET",
        payload: dict | None = None,
        verify: bool = False,
        timeout: int = 30,
    ) -> dict:
        """Request a path via Redfish against the Bmc."""
        url = f"{self.url()}{path}"
        r = requests.request(
            method,
            url,
            auth=(self.username, self.password),
            verify=verify,
            timeout=timeout,
            json=payload,
            headers=HEADERS,
        )
        if r.status_code >= 400:
            raise RedfishRequestError(
                f"BMC communications failure HTTP {r.status_code} "
                + f"{r.reason} from {url} - {r.text}"
            )
        if r.text:
            return r.json()
        else:
            return {}

    def sushy(self):
        """Return a Sushy interface to BMC."""
        return Sushy(
            self.url(), username=self.username, password=self.password, verify=False
        )


def bmc_for_ip_address(
    ip_address: str, username: str = "root", password: str | None = None
) -> Bmc:
    """Factory method to create a Bmc object with a standard password.

    If no password is supplied then we use a conventional BMC standard one
    which is derived from the IP address and the BMC_MASTER secret key.

    If no username is supplied then the username "root" is used.
    """
    if password is None:
        bmc_master = os.getenv("BMC_MASTER") or credential("bmc_master", "key")
        password = standard_password(ip_address, bmc_master)

    return Bmc(
        ip_address=ip_address,
        password=password,
        username=username,
    )
