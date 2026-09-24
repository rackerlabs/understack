import importlib.metadata
import urllib.parse

import requests
from oslo_config import cfg
from oslo_log import log
from requests.models import HTTPError

from neutron_understack import config

LOG = log.getLogger(__name__)


class UndersyncError(Exception):
    pass


class Undersync:
    def __init__(
        self,
        api_url: str | None = None,
        timeout: int = 90,
    ) -> None:
        self.url = "http://undersync.undersync.svc.cluster.local:8080"
        self.api_url = api_url or self.url
        self.timeout = timeout

        version = importlib.metadata.version("neutron_understack")

        # we use the [ironic] group here since we don't need to duplicate
        # the credentials
        config.register_ironic_opts(cfg.CONF)
        config.register_ml2_understack_opts(cfg.CONF)
        self._session = config.get_session(config._OPT_GRP_IRONIC)
        self._session.app_name = "neutron_understack"
        self._session.app_version = version

    def _log_and_raise_for_status(self, response: requests.Response):
        try:
            response.raise_for_status()
        except HTTPError as error:
            LOG.error("Undersync error: %(error)s", {"error": error})
            raise UndersyncError() from error

    def _undersync_post(self, action: str, vlan_group: str) -> requests.Response:
        vlan_group = urllib.parse.quote(vlan_group, safe="")
        response = self._session.post(
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
        if cfg.CONF.ml2_understack.undersync_dry_run:
            return self._undersync_post("dry-run", vlan_group)
        return self._undersync_post("sync", vlan_group)

    def dry_run(self, vlan_group: str) -> requests.Response:
        return self._undersync_post("dry-run", vlan_group)

    def force(self, vlan_group: str) -> requests.Response:
        return self._undersync_post("force", vlan_group)
