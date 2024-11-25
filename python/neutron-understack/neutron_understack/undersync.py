import pathlib
from functools import cached_property

import requests
from oslo_log import log
from requests.models import HTTPError

LOG = log.getLogger(__name__)


class UndersyncError(Exception):
    pass


class Undersync:
    def __init__(
        self,
        auth_token: str | None = None,
        api_url: str | None = None,
        timeout: int = 90,
    ) -> None:
        """Simple client for Undersync."""
        self.token = auth_token or self._fetch_undersync_token()
        self.url = "http://undersync-service.undersync.svc.cluster.local:8080"
        self.api_url = api_url or self.url
        self.timeout = timeout

    def _fetch_undersync_token(self) -> str:
        file = pathlib.Path("/etc/undersync/token")
        with file.open() as f:
            return f.read().strip()

    def _log_and_raise_for_status(self, response: requests.Response):
        try:
            response.raise_for_status()
        except HTTPError as error:
            LOG.error("Undersync error: %(error)s", {"error": error})
            raise UndersyncError() from error

    def sync_devices(
        self, vlan_group_uuids: str | list[str], force=False, dry_run=False
    ) -> requests.Response:
        if isinstance(vlan_group_uuids, list):
            vlan_group_uuids = ",".join(vlan_group_uuids)

        if dry_run:
            return self.dry_run(vlan_group_uuids)
        elif force:
            return self.force(vlan_group_uuids)
        else:
            return self.sync(vlan_group_uuids)

    @cached_property
    def client(self):
        session = requests.Session()
        session.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}",
        }
        return session

    def _undersync_post(self, action: str, uuids: str) -> requests.Response:
        response = self.client.post(
            f"{self.api_url}/v1/vlan-group/{uuids}/{action}", timeout=self.timeout
        )
        LOG.debug(
            "undersync %(action)s resp: %(resp)s",
            {"resp": response.json(), "action": action},
        )
        self._log_and_raise_for_status(response)
        return response

    def sync(self, uuids: str) -> requests.Response:
        return self._undersync_post("sync", uuids)

    def dry_run(self, uuids: str) -> requests.Response:
        return self._undersync_post("dry-run", uuids)

    def force(self, uuids: str) -> requests.Response:
        return self._undersync_post("force", uuids)
