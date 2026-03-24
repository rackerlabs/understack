from functools import cached_property
from urllib.parse import quote

import requests


class Undersync:
    def __init__(
        self,
        auth_token: str,
        api_url="http://undersync-service.undersync.svc.cluster.local:8080",
    ) -> None:
        """Simple client for Undersync."""
        self.token = auth_token
        self.api_url = api_url

    def sync_devices(self, physical_network: str, force=False, dry_run=False):
        if dry_run:
            return self.dry_run(physical_network)
        elif force:
            return self.force(physical_network)
        else:
            return self.sync(physical_network)

    @cached_property
    def client(self):
        session = requests.Session()
        session.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        return session

    def sync(self, physical_network: str) -> requests.Response:
        physnet = quote(physical_network, safe="")
        response = self.client.post(f"{self.api_url}/v1/vlan-group/{physnet}/sync")
        response.raise_for_status()
        return response

    def dry_run(self, physical_network: str) -> requests.Response:
        physnet = quote(physical_network, safe="")
        response = self.client.post(f"{self.api_url}/v1/vlan-group/{physnet}/dry-run")
        response.raise_for_status()
        return response

    def force(self, physical_network: str) -> requests.Response:
        physnet = quote(physical_network, safe="")
        response = self.client.post(f"{self.api_url}/v1/vlan-group/{physnet}/force")
        response.raise_for_status()
        return response
