import pathlib
from urllib.parse import urljoin

import requests
from oslo_log import log

LOG = log.getLogger(__name__)


class Nautobot:
    def __init__(self, nb_url: str | None = None, nb_token: str | None = None):
        """Basic Nautobot wrapper because pynautobot doesn't expose plugin APIs."""
        self.base_url = nb_url or "http://nautobot-default.nautobot.svc.cluster.local"
        self.token = nb_token or self.fetch_nb_token()
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Token {self.token}"})

    def fetch_nb_token(self):
        file = pathlib.Path("/etc/nb-token/token")
        with file.open() as f:
            return f.read().strip()

    def ucvni_create(
        self,
        network_id: str,
        ucvni_group: str,
        network_name: str,
        segment_id: int | None = None,
    ):
        payload = {
            "id": network_id,
            "name": network_name,
            "ucvni_group": ucvni_group,
            "status": "Active",
        }

        if segment_id:
            payload["ucvni_id"] = segment_id
            payload["ucvni_type"] = "INFRA"

        url = urljoin(self.base_url, "/api/plugins/undercloud-vni/ucvnis/")
        LOG.debug("ucvni_create payload: %(payload)s", {"payload": payload})
        resp = self.s.post(url, json=payload, timeout=10)
        LOG.debug("ucvni_create resp: %(resp)s", {"resp": resp.json()})
        resp.raise_for_status()
