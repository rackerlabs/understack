from dataclasses import dataclass
from understack_workflows.helpers import credential
from understack_workflows.bmc_password_standard import standard_password
from sushy import Sushy


@dataclass
class Bmc
    ip_address: str
    bmc_type: str
    username: str = "root"
    password: str

    def url(self):
        return f"https://{self.ip_address}"

    def sushy_session(self, verify=False) -> Sushy:
        return Sushy(
            self.url()
            verify=verify,
            username=self.username,
            password=self.password,
        )

    def redfish_request(self,
        path: str,
        method: str = "GET",
        payload: Dict | None = None,
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
