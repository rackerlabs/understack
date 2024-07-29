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

    def sync_devices(self, switch_hostnames: list[str], force=False, dry_run=False):
        if dry_run:
            return [self.dry_run(hostname) for hostname in switch_hostnames]
        elif force:
            return [self.force(hostname) for hostname in switch_hostnames]
        else:
            return [self.sync(hostname) for hostname in switch_hostnames]

    @cached_property
    def client(self):
        session = requests.Session()
        session.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        return session

    def sync(self, hostname: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/devices/{hostname}/sync")
        response.raise_for_status()
        return response

    def dry_run(self, hostname: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/devices/{hostname}/dry-run")
        response.raise_for_status()
        return response

    def force(self, hostname: str) -> requests.Response:
        response = self.client.post(f"{self.api_url}/v1/devices/{hostname}/force")
        response.raise_for_status()
        return response
