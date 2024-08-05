from functools import cached_property

import requests


class Undersync:
    def __init__(
        self,
        auth_token: str,
        api_url="http://undersync-service.undersync.svc.cluster.local:8080",
    ) -> None:
        self.token = auth_token
        self.api_url = api_url

    def sync_devices(self, switch_uuids: str | list[str], force=False, dry_run=False):
        if isinstance(switch_uuids, list):
            switch_uuids = ",".join(switch_uuids)

        if dry_run:
            return self.dry_run(switch_uuids)
        elif force:
            return self.force(switch_uuids)
        else:
            return self.sync(switch_uuids)

    @cached_property
    def client(self):
        session = requests.Session()
        session.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        return session

    def sync(self, uuids: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/devices/{uuids}/sync")
        response.raise_for_status()
        return response

    def dry_run(self, uuids: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/devices/{uuids}/dry-run")
        response.raise_for_status()
        return response

    def force(self, uuids: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/devices/{uuids}/force")
        response.raise_for_status()
        return response
