from functools import cached_property

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

    def sync_devices(self, vlan_group_uuid: str, force=False, dry_run=False):
        if dry_run:
            return self.dry_run(vlan_group_uuid)
        elif force:
            return self.force(vlan_group_uuid)
        else:
            return self.sync(vlan_group_uuid)

    @cached_property
    def client(self):
        session = requests.Session()
        session.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        return session

    def sync(self, uuids: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/vlan-group/{uuids}/sync")
        response.raise_for_status()
        return response

    def dry_run(self, uuids: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/vlan-group/{uuids}/dry-run")
        response.raise_for_status()
        return response

    def force(self, uuids: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/vlan-group/{uuids}/force")
        response.raise_for_status()
        return response
