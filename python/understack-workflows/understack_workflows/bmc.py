from dataclasses import dataclass
import os
import logging
import requests

from sushy import Sushy
from understack_workflows.bmc_password_standard import standard_password
from understack_workflows.helpers import credential

logging.getLogger("urllib3").setLevel(logging.WARNING)

HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json; charset=utf-8",
}

@dataclass
class Bmc:
    ip_address: str
    username: str
    password: str

    def __str__(self):
        return f"BMC {self.url()}"

    def url(self):
        return f"https://{self.ip_address}"

    def redfish_request(self,
        path: str,
        method: str = "GET",
        payload: dict | None = None,
        verify: bool = False,
        timeout: int = 30,
    ) -> dict:
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
            raise Exception(
                f"BMC communications failure HTTP {r.status_code} "
                f"{r.reason} from {url} - {r.text}"
            )
        if r.text:
            return r.json()

    def sushy(self):
        return Sushy(self.url(), username=self.username, password=self.password, verify=False)

def bmc_for_ip_address(
        ip_address: str,
        username: str = "root",
        password: str|None = None) -> Bmc:

    if password is None:
        bmc_master = os.getenv("BMC_MASTER") or credential("bmc_master", "key")
        password = standard_password(ip_address, bmc_master)

    return Bmc(
        ip_address=ip_address,
        password=password,
        username=username,
    )
