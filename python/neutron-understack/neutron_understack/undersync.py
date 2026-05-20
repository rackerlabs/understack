import pathlib
import urllib.parse

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
        use_keystone_auth: bool = False,
        session=None,
    ) -> None:
        """Simple client for Undersync.

        Args:
            auth_token: Authentication token. If use_keystone_auth is True,
                       this should be a Keystone service token. Otherwise,
                       it should be a JWT token. If not provided, it will be
                       fetched from /etc/undersync/token.
            api_url: Undersync API URL.
            timeout: Request timeout in seconds.
            use_keystone_auth: If True, use X-Auth-Token header for Keystone
                             authentication. Otherwise, use Authorization:
                             Bearer header for JWT authentication.
            session: Keystone session object for automatic token refresh.
                    If provided, takes precedence over auth_token for Keystone auth.
        """
        self.session = session
        self.token = auth_token or (
            self._fetch_undersync_token() if not session else None
        )
        self.url = "http://undersync.undersync.svc.cluster.local:8080"
        self.api_url = api_url or self.url
        self.timeout = timeout
        self.use_keystone_auth = use_keystone_auth

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
        self, vlan_group: str, force=False, dry_run=False
    ) -> requests.Response:
        if dry_run:
            return self.dry_run(vlan_group)
        elif force:
            return self.force(vlan_group)
        else:
            return self.sync(vlan_group)

    @property
    def client(self):
        session = requests.Session()
        session.headers = {"Content-Type": "application/json"}

        if self.use_keystone_auth and self.session:
            # Get fresh token from session for each request (enables refresh)
            token = self.session.get_token()
            session.headers["X-Auth-Token"] = token
        elif self.use_keystone_auth:
            # Fallback to stored token for backward compatibility
            session.headers["X-Auth-Token"] = self.token
        else:
            session.headers["Authorization"] = f"Bearer {self.token}"

        return session

    def _undersync_post(self, action: str, vlan_group: str) -> requests.Response:
        vlan_group = urllib.parse.quote(vlan_group, safe="")
        response = self.client.post(
            f"{self.api_url}/v1/vlan-group/{vlan_group}/{action}", timeout=self.timeout
        )
        try:
            LOG.debug(
                "undersync %(action)s resp: %(resp)s",
                {"resp": response.json(), "action": action},
            )
        except requests.exceptions.JSONDecodeError:
            LOG.debug("undersync %s non-JSON resp: %s", action, response.text)
        self._log_and_raise_for_status(response)
        return response

    def sync(self, vlan_group: str) -> requests.Response:
        return self._undersync_post("sync", vlan_group)

    def dry_run(self, vlan_group: str) -> requests.Response:
        return self._undersync_post("dry-run", vlan_group)

    def force(self, vlan_group: str) -> requests.Response:
        return self._undersync_post("force", vlan_group)
