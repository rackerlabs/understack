from urllib.parse import urljoin

import requests
from oslo_log import log

LOG = log.getLogger(__name__)


class Nautobot:
    def __init__(self, nb_url: str, nb_token: str):
        """Basic Nautobot wrapper because pynautobot doesn't expose plugin APIs."""
        self.base_url = nb_url
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Token {nb_token}"})

    def ucvni_create(
        self, network_id: str, segment_id: int, ucvni_group: str, network_name: str
    ):
        payload = {
            "id": network_id,
            "ucvni_id": segment_id,
            "name": network_name,
            "ucvni_group": ucvni_group,
            "status": "Active",
        }

        url = urljoin(self.base_url, "/api/plugins/undercloud-vni/ucvnis/")
        LOG.debug("ucvni_create payload: %(payload)s", {"payload": payload})
        resp = self.s.post(url, json=payload, timeout=10)
        LOG.debug("ucvni_create resp: %(resp)s", {"resp": resp.json()})
        resp.raise_for_status()
