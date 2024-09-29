import requests
from dataclasses import dataclass
from understack_workflows.helpers import credential
from understack_workflows.bmc_password_standard import standard_password

@dataclass
class Bmc:
    ip_address: str
    bmc_type: str
    username: str
    password: str

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
        r.raise_for_status()
        return r.json()

def bmc_for_ip_address(ip_address: str, bmc_type: str, username: str = "root") -> Bmc:
    bmc_master_key = credential("bmc_master", "key")
    password = standard_password(ip_address, bmc_master_key)
    return Bmc(bmc_type=bmc_type, ip_address=ip_address, password=password, username=username)
