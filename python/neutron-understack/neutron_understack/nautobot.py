import inspect
import pathlib
from urllib.parse import urljoin
from uuid import UUID

import requests
from neutron_lib import exceptions as exc
from oslo_log import log
from requests.models import HTTPError

LOG = log.getLogger(__name__)


class NautobotRequestError(exc.NeutronException):
    message = "HTTP %(code)s for %(obj)s in Nautobot. ref=%(ref)s err=%(err)s"

    def __init__(self, code: int, obj: str, ref: str, err: str):
        super().__init__(code=code, obj=obj, ref=ref, err=err)


class NautobotOSError(exc.NeutronException):
    message = "Error occurred while querying Nautobot URL %(url)s %(err)s"

    def __init__(self, url: str, err: str):
        super().__init__(url=url, err=err)


class NautobotNotFoundError(exc.NeutronException):
    message = "%(obj)s not found in Nautobot. ref=%(ref)s"

    def __init__(self, obj: str, ref: str):
        super().__init__(obj=obj, ref=ref)


def _requests_to_exc(e: HTTPError, obj: str, ref: str):
    try:
        err = e.response.json()["error"]
    except Exception:
        err = e.response.content

    return NautobotRequestError(e.response.status_code, obj, ref, err)


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

    def make_api_request(
        self, url: str, method: str, payload: dict | None = None, params=None
    ) -> dict:
        endpoint_url = urljoin(self.base_url, url)
        caller_function = inspect.stack()[self.CALLER_FRAME].function
        http_method = method.upper()

        LOG.debug(
            "%(caller_function)s payload: %(payload)s",
            {"payload": payload, "caller_function": caller_function},
        )
        resp = self.s.request(
            http_method, endpoint_url, timeout=10, json=payload, params=params
        )

        if resp.content:
            resp_data = resp.json()
        else:
            resp_data = {"status_code": resp.status_code}

        LOG.debug(
            "%(caller_function)s resp: %(resp)s",
            {"resp": resp_data, "caller_function": caller_function},
        )
        resp.raise_for_status()
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
        try:
            return self.make_api_request(url, "post", payload)
        except HTTPError as e:
            raise _requests_to_exc(e, "ucvni", str(payload)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

    def ucvni_delete(self, network_id):
        url = f"/api/plugins/undercloud-vni/ucvnis/{network_id}/"
        try:
            return self.make_api_request(url, "delete")
        except HTTPError as e:
            raise _requests_to_exc(e, "ucvni", str(network_id)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

    def fetch_namespace_by_name(self, name: str) -> str:
        url = f"/api/ipam/namespaces/?name={name}&depth=1"
        try:
            resp_data = self.make_api_request(url, "get")
        except HTTPError as e:
            raise _requests_to_exc(e, "namespace", str(name)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e
        try:
            return resp_data["results"][0]["id"]
        except (IndexError, KeyError) as e:
            raise NautobotNotFoundError("namespace", name) from e

    def namespace_create(self, name: str) -> dict:
        url = "/api/ipam/namespaces/"
        payload = {"name": name}
        try:
            return self.make_api_request(url, "post", payload)
        except HTTPError as e:
            raise _requests_to_exc(e, "namespace", name) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

    def namespace_delete(self, namespace_uuid: str) -> dict:
        url = f"/api/ipam/namespaces/{namespace_uuid}/"
        try:
            return self.make_api_request(url, "delete")
        except HTTPError as e:
            raise _requests_to_exc(e, "namespace", namespace_uuid) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

    def subnet_create(self, subnet_uuid: str, prefix: str, namespace_name: str) -> dict:
        url = "/api/ipam/prefixes/"
        payload = {
            "id": subnet_uuid,
            "prefix": prefix,
            "status": "Active",
            "namespace": {"name": namespace_name},
        }
        try:
            return self.make_api_request(url, "post", payload)
        except HTTPError as e:
            raise _requests_to_exc(e, "prefix", str(payload)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

    def subnet_delete(self, subnet_uuid: str) -> dict:
        url = f"/api/ipam/prefixes/{subnet_uuid}/"
        try:
            return self.make_api_request(url, "delete")
        except HTTPError as e:
            raise _requests_to_exc(e, "prefix", str(subnet_uuid)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

    def prep_switch_interface(
        self,
        connected_interface_id: str,
        ucvni_uuid: str,
        vlan_tag: int | None,
        modify_native_vlan: bool | None = True,
    ) -> dict:
        """Runs a Nautobot Job to update a switch interface for tenant mode.

        The nautobot job will assign vlans as required and set the interface
        into the correct mode for "normal" tenant operation.

        The dictionary with vlan group ID and vlan tag is returned.
        """
        url = "/api/plugins/undercloud-vni/prep_switch_interface"
        payload = {
            "ucvni_id": str(ucvni_uuid),
            "connected_interface_id": str(connected_interface_id),
            "modify_native_vlan": modify_native_vlan,
            "vlan_tag": vlan_tag,
        }
        try:
            return self.make_api_request(url, "post", payload)
        except HTTPError as e:
            raise _requests_to_exc(e, "prep_switch_interface", str(payload)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

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
        try:
            resp_data = self.make_api_request(url, "post", payload)
        except HTTPError as e:
            raise _requests_to_exc(e, "detach port", str(payload)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

        return resp_data["vlan_group_id"]

    def configure_port_status(self, interface_uuid: str, status: str) -> dict:
        url = f"/api/dcim/interfaces/{interface_uuid}/"
        payload = {"status": {"name": status}}
        try:
            resp_data = self.make_api_request(url, "patch", payload)
        except HTTPError as e:
            raise _requests_to_exc(e, "configure port status", str(payload)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e
        return resp_data

    def fetch_vlan_group_uuid(self, device_uuid: str) -> str:
        url = f"/api/dcim/devices/{device_uuid}/?include=relationships"

        try:
            resp_data = self.make_api_request(url, "get")
        except HTTPError as e:
            raise _requests_to_exc(e, "device", str(device_uuid)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e

        try:
            vlan_group_uuid = resp_data["relationships"]["vlan_group_to_devices"][
                "source"
            ]["objects"][0]["id"]
        except (KeyError, IndexError, TypeError) as e:
            raise NautobotNotFoundError(
                "vlan_group for device", str(device_uuid)
            ) from e

        LOG.debug(
            "vlan_group_uuid: %(vlan_group_uuid)s", {"vlan_group_uuid": vlan_group_uuid}
        )
        return vlan_group_uuid

    def check_vlan_availability(self, interface_id: str | UUID, vlan_tag: int) -> bool:
        """Checks if particular vlan_tag is available in a fabric.

        This method checks if a VLAN number, specified as `vlan_tag`, is used
        in any of the VLAN groups associated with the fabric to which the
        interface, identified by `interface_id`, is connected.
        """
        url = "/api/plugins/undercloud-vni/vlan_availability_check"
        params = {
            "interface_id": str(interface_id),
            "vlan_tag": int(vlan_tag),
        }
        try:
            response = self.make_api_request(url, "get", params=params)
        except HTTPError as e:
            raise _requests_to_exc(e, "VLAN availability", str(params)) from e
        except OSError as e:
            raise NautobotOSError(url, str(e)) from e
        if not response:
            return False
        return response.get("available", False)
