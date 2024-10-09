import requests
from dataclasses import dataclass
from understack_workflows.helpers import credential
from sushy import Sushy

@dataclass
class Bmc:
    ip_address: str
    bmc_type: str
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
            json=payload
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
        bmc_type: str = None,
        username: str = "root",
        password: str|None = None) -> Bmc:

    if password is None:
        username = credential("oob-secrets", "username")
        password = credential("oob-secrets", "password")

    return Bmc(bmc_type=bmc_type, ip_address=ip_address, password=password, username=username)
