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
            "status": {"name": "Active"},
        }

        if segment_id:
            payload["ucvni_id"] = segment_id
            payload["ucvni_type"] = "INFRA"

        url = urljoin(self.base_url, "/api/plugins/undercloud-vni/ucvnis/")
        LOG.debug("ucvni_create payload: %(payload)s", {"payload": payload})
        resp = self.s.post(url, json=payload, timeout=10)
        LOG.debug("ucvni_create resp: %(resp)s", {"resp": resp.json()})
        resp.raise_for_status()

    def ucvni_delete(self, network_id):
        payload = {"id": network_id}

        ucvni_url = f"/api/plugins/undercloud-vni/ucvnis/{network_id}/"
        url = urljoin(self.base_url, ucvni_url)
        LOG.debug("ucvni_delete payload: %(payload)s", {"payload": payload})
        resp = self.s.delete(url, json=payload, timeout=10)
        LOG.debug("ucvni_delete resp: %(resp)s", {"resp": resp.status_code})
        resp.raise_for_status()

    def detach_port(self, network_id, mac_address):
        payload = {
            "ucvni_uuid": network_id,
            "server_interface_mac": mac_address,
        }

        url = urljoin(self.base_url, "/api/plugins/undercloud-vni/detach_port")
        LOG.debug("detach_port payload: %(payload)s", {"payload": payload})
        resp = self.s.post(url, json=payload, timeout=10)
        resp_data = resp.json()
        LOG.debug("detach_port resp: %(resp)s", {"resp": resp_data})
        resp.raise_for_status()
        return resp_data["vlan_group_id"]

    def reset_port_status(self, mac_address):
        intf_url = urljoin(
            self.base_url, f"/api/dcim/interfaces/?mac_address={mac_address}"
        )
        intf_resp = self.s.get(intf_url, timeout=10)
        intf_resp_data = intf_resp.json()

        LOG.debug("reset_port interface resp: %(resp)s", {"resp": intf_resp_data})
        intf_resp.raise_for_status()

        conn_intf_url = intf_resp_data["results"][0]["connected_endpoint"]["url"]

        payload = {"status": {"name": "Active"}}
        resp = self.s.patch(conn_intf_url, json=payload, timeout=10)

        LOG.debug(
            "reset_port connected interface resp: %(resp)s", {"resp": resp.json()}
        )
        resp.raise_for_status()
