import inspect
import pathlib
from urllib.parse import urljoin

import requests
from neutron_lib import exceptions as exc
from oslo_log import log
from requests.models import HTTPError

LOG = log.getLogger(__name__)


class NautobotError(exc.NeutronException):
    message = "Nautobot error"


class NautobotNotFoundError(NautobotError):
    message = "%(obj)s not found in Nautobot. ref=%(ref)s"


class Nautobot:
    CALLER_FRAME = 1

    def __init__(self, nb_url: str | None = None, nb_token: str | None = None):
        """Basic Nautobot wrapper because pynautobot doesn't expose plugin APIs."""
        self.base_url = nb_url or "http://nautobot-default.nautobot.svc.cluster.local"
        self.token = nb_token or self._fetch_nb_token()
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Token {self.token}"})

    def _fetch_nb_token(self):
        file = pathlib.Path("/etc/nb-token/token")
        with file.open() as f:
            return f.read().strip()

    def _log_and_raise_for_status(self, response):
        try:
            response.raise_for_status()
        except HTTPError as error:
            LOG.error("Nautobot error: %(error)s", {"error": error})
            raise NautobotError() from error

    def make_api_request(
        self, url: str, method: str, payload: dict | None = None
    ) -> dict:
        endpoint_url = urljoin(self.base_url, url)
        caller_function = inspect.stack()[self.CALLER_FRAME].function
        http_method = method.upper()

        LOG.debug(
            "%(caller_function)s payload: %(payload)s",
            {"payload": payload, "caller_function": caller_function},
        )
        resp = self.s.request(http_method, endpoint_url, timeout=10, json=payload)

        if resp.content:
            resp_data = resp.json()
        else:
            resp_data = {"status_code": resp.status_code}

        LOG.debug(
            "%(caller_function)s resp: %(resp)s",
            {"resp": resp_data, "caller_function": caller_function},
        )
        self._log_and_raise_for_status(resp)
        return resp_data

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

        url = "/api/plugins/undercloud-vni/ucvnis/"
        resp_data = self.make_api_request(url, "post", payload)
        return resp_data

    def ucvni_delete(self, network_id):
        url = f"/api/plugins/undercloud-vni/ucvnis/{network_id}/"
        return self.make_api_request(url, "delete")

    def fetch_namespace_by_name(self, name: str) -> str:
        url = f"/api/ipam/namespaces/?name={name}&depth=1"
        resp_data = self.make_api_request(url, "get")
        try:
            return resp_data["results"][0]["id"]
        except (IndexError, KeyError) as error:
            LOG.error("Nautobot error: %(error)s", {"error": error})
            raise NautobotNotFoundError(obj="namespace", ref=name) from error

    def namespace_create(self, name: str) -> dict:
        url = "/api/ipam/namespaces/"
        payload = {"name": name}
        return self.make_api_request(url, "post", payload)

    def namespace_delete(self, namespace_uuid: str) -> dict:
        url = f"/api/ipam/namespaces/{namespace_uuid}/"
        return self.make_api_request(url, "delete")

    def subnet_create(self, subnet_uuid: str, prefix: str, namespace_name: str) -> dict:
        url = "/api/ipam/prefixes/"
        payload = {
            "id": subnet_uuid,
            "prefix": prefix,
            "status": "Active",
            "namespace": {"name": namespace_name},
        }
        return self.make_api_request(url, "post", payload)

    def subnet_delete(self, subnet_uuid: str) -> dict:
        url = f"/api/ipam/prefixes/{subnet_uuid}/"
        return self.make_api_request(url, "delete")

    def prep_switch_interface(
        self, connected_interface_id: str, ucvni_uuid: str
    ) -> str:
        """Runs a Nautobot Job to update a switch interface for tenant mode.

        The nautobot job will assign vlans as required and set the interface
        into the correct mode for "normal" tenant operation.

        The vlan group ID is returned.
        """
        url = "/api/plugins/undercloud-vni/prep_switch_interface"
        payload = {
            "ucvni_id": str(ucvni_uuid),
            "connected_interface_id": str(connected_interface_id),
        }
        resp_data = self.make_api_request(url, "post", payload)

        return resp_data["vlan_group_id"]

    def detach_port(self, connected_interface_id: str, ucvni_uuid: str) -> str:
        """Runs a Nautobot Job to cleanup a switch interface.

        The nautobot job will find a VLAN that is bound to the UCVNI, remove it
        from the Interface and if the VLAN is unused it will delete it.

        The vlan group ID is returned.
        """
        url = "/api/plugins/undercloud-vni/detach_port"
        payload = {
            "ucvni_uuid": str(ucvni_uuid),
            "connected_interface_id": str(connected_interface_id),
        }
        resp_data = self.make_api_request(url, "post", payload)

        return resp_data["vlan_group_id"]

    def configure_port_status(self, interface_uuid: str, status: str) -> dict:
        url = f"/api/dcim/interfaces/{interface_uuid}/"
        payload = {"status": {"name": status}}
        resp_data = self.make_api_request(url, "patch", payload)
        return resp_data

    def fetch_vlan_group_uuid(self, device_uuid: str) -> str:
        url = f"/api/dcim/devices/{device_uuid}/?include=relationships"

        resp_data = self.make_api_request(url, "get")
        try:
            vlan_group_uuid = resp_data["relationships"]["vlan_group_to_devices"][
                "source"
            ]["objects"][0]["id"]
        except (KeyError, IndexError, TypeError) as error:
            LOG.error("vlan_group_uuid_error: %(error)s", {"error": error})
            raise NautobotError() from error

        LOG.debug(
            "vlan_group_uuid: %(vlan_group_uuid)s", {"vlan_group_uuid": vlan_group_uuid}
        )
        return vlan_group_uuid
