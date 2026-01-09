# pylint: disable=E1131,C0103

import copy
import logging
import os
from dataclasses import dataclass

import requests
import urllib3
from sushy import Sushy

from understack_workflows.bmc_password_standard import standard_password
from understack_workflows.helpers import credential
from understack_workflows.helpers import setup_logger

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)  # type: ignore
logging.getLogger("urllib3").setLevel(logging.WARNING)

logger = setup_logger(__name__)

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json; charset=utf-8",
}


class RedfishRequestError(Exception):
    """Handle Exceptions from Redfish handler."""


class AuthException(Exception):
    """Authentication Exception."""


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
        self._base_path: str | None = None
        self._system_path: str | None = None
        self._manager_path: str | None = None

    @property
    def base_path(self) -> str:
        """Read System path from BMC."""
        self._system_path = self._base_path or self.get_base_path()
        return self._system_path

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

    def get_base_path(self):
        """Get Base Path."""
        _result = "/redfish/v1"
        return _result

    def get_system_path(self):
        """Get System Path."""
        _result = self.redfish_request("/redfish/v1/Systems/")
        return _result["Members"][0]["@odata.id"].rstrip("/")

    def get_manager_path(self):
        """Get Manager Path."""
        _result = self.redfish_request("/redfish/v1/Managers/")
        return _result["Members"][0]["@odata.id"].rstrip("/")

    def get_user_accounts(self, token: str | None = None) -> list[dict]:
        """A vendor agnostic approach to crawling the API for BMC accounts."""
        path = self.base_path
        path = self.redfish_request(path, token=token)["AccountService"]["@odata.id"]
        path = self.redfish_request(path, token=token)["Accounts"]["@odata.id"]
        return self.redfish_request(path, token=token)["Members"]

    def set_bmc_creds(self, password: str, token: str | None = None):
        """Change password for the account associated with the bmc."""
        accounts = self.get_user_accounts(token)
        matched_account = None
        for account in accounts:
            account_url = account["@odata.id"]
            a = self.redfish_request(path=account_url, token=token)
            if self.username == a["UserName"]:
                logger.debug("found account: %s", a)
                matched_account = a
                break
        if not matched_account:
            raise AuthException(f"Unable to find BMC account for {self.username}")
        account_uri = matched_account["@odata.id"]
        _payload = {"Password": password}
        self.redfish_request(
            method="PATCH", path=account_uri, token=token, payload=_payload
        )

    def get_session(self, password: str) -> tuple[str, str] | tuple[None, None]:
        """Request a new session."""
        _payload = {"UserName": self.username, "Password": password}
        token, session = self.session_request(
            method="POST",
            path="/redfish/v1/SessionService/Sessions",
            payload=_payload,
        )
        if token and session:
            return token, session
        else:
            return None, None

    def close_session(self, session: str, token: str | None = None) -> None:
        """Close BMC token session."""
        self.redfish_request(method="DELETE", path=session, token=token)

    def session_request(
        self,
        path: str,
        method: str = "POST",
        payload: dict | None = None,
        verify: bool = False,
        timeout: int = 30,
    ) -> tuple[str, str] | tuple[None, None]:
        """Request a session via Redfish against the Bmc."""
        _headers = copy.copy(HEADERS)
        url = f"{self.url()}{path}"
        r = requests.request(
            method,
            url,
            verify=verify,
            timeout=timeout,
            json=payload,
            headers=_headers,
        )
        if r.status_code >= 400:
            raise RedfishRequestError(
                f"BMC communications failure HTTP {r.status_code} "
                + f"{r.reason} from {url} - {r.text}"
            )
        if r.text:
            token = r.headers["X-Auth-Token"]
            if "Location" in r.headers:
                location = r.headers["Location"].split(self.ip_address)[1]
            else:
                location = r.json()["@odata.id"]

            return (token, location)
        else:
            return (None, None)

    def redfish_request(
        self,
        path: str,
        method: str = "GET",
        payload: dict | None = None,
        token: str | None = None,
        verify: bool = False,
        timeout: int = 30,
    ) -> dict:
        """Request a path via Redfish against the Bmc."""
        _headers = copy.copy(HEADERS)
        if token:
            _headers.update({"X-Auth-Token": token})
        url = f"{self.url()}{path}"
        r = requests.request(
            method,
            url,
            auth=None if token else (self.username, self.password),
            verify=verify,
            timeout=timeout,
            json=payload,
            headers=_headers,
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
