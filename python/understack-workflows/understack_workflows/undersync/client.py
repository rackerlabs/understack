from urllib.parse import quote

import requests
from keystoneauth1.session import Session


class Undersync:
    def __init__(
        self,
        session: Session,
        api_url="http://undersync.undersync.svc.cluster.local:8080",
        timeout: int = 90,
    ) -> None:
        """Simple client for Undersync.

        Authenticates with the OpenStack credentials from the supplied
        keystoneauth1 session, which handles token refresh transparently.
        """
        self.session = session
        self.api_url = api_url
        self.timeout = timeout

    def sync_devices(self, physical_network: str, force=False, dry_run=False):
        if dry_run:
            return self.dry_run(physical_network)
        elif force:
            return self.force(physical_network)
        else:
            return self.sync(physical_network)

    def _post(self, action: str, physical_network: str) -> requests.Response:
        physnet = quote(physical_network, safe="")
        response = self.session.post(
            f"{self.api_url}/v1/vlan-group/{physnet}/{action}", timeout=self.timeout
        )
        response.raise_for_status()
        return response

    def sync(self, physical_network: str) -> requests.Response:
        return self._post("sync", physical_network)

    def dry_run(self, physical_network: str) -> requests.Response:
        return self._post("dry-run", physical_network)

    def force(self, physical_network: str) -> requests.Response:
        return self._post("force", physical_network)
