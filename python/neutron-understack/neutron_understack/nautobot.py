import inspect
from urllib.parse import urljoin
from uuid import UUID

import requests
from neutron_lib import exceptions as exc
from oslo_log import log

LOG = log.getLogger(__name__)



class NautobotRequestError(exc.NeutronException):
    message = "Nautobot API returned error %(code)s for %(url)s: %(body)s"


class NautobotOSError(exc.NeutronException):
    message = "Error occurred querying Nautobot: %(err)s"


class NautobotNotFoundError(exc.NeutronException):
    message = "%(obj)s not found in Nautobot. ref=%(ref)s"


class Nautobot:
    """Basic Nautobot wrapper because pynautobot doesn't expose plugin APIs."""

    def __init__(self, nb_url: str, nb_token: str):
        self.base_url = nb_url
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {nb_token}"})

    def make_api_request(
        self,
        method: str,
        url: str,
        payload: dict | None = None,
        params: dict[str, str] | None = None,
        timeout: int = 10,
    ) -> dict:
        full_url = urljoin(self.base_url, url)

        try:
            response = self.session.request(
                method,
                full_url,
                timeout=timeout,
                json=payload,
                params=params,
                allow_redirects=False,
            )
        except Exception as e:
            raise NautobotOSError(err=e) from e

        if response.status_code >= 300:
            raise NautobotRequestError(
                code=response.status_code, url=full_url, body=response.content
            )
        if not response.content:
            data = {"status_code": response.status_code}
        try:
            data = response.json()
        except requests.exceptions.JSONDecodeError:
            data = {"body": response.content}

        caller_function = inspect.stack()[1].function
        LOG.debug(
            "[%s] %s %s %s ==> %s", caller_function, full_url, method, payload, data
        )
        return data

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
        return self.make_api_request("POST", url, payload)

    def ucvni_delete(self, network_id):
        url = f"/api/plugins/undercloud-vni/ucvnis/{network_id}/"
        return self.make_api_request("DELETE", url)

    def fetch_namespace_by_name(self, name: str) -> str:
        url = f"/api/ipam/namespaces/?name={name}&depth=1"
        resp_data = self.make_api_request("GET", url)
        try:
            return resp_data["results"][0]["id"]
        except (IndexError, KeyError) as error:
            raise NautobotNotFoundError(obj="namespace", ref=name) from error

    def namespace_create(self, name: str) -> dict:
        payload = {"name": name}
        return self.make_api_request("POST", "/api/ipam/namespaces/", payload)

    def namespace_delete(self, uuid: str) -> dict:
        return self.make_api_request("DELETE", f"/api/ipam/namespaces/{uuid}/")

    def subnet_create(self, subnet_uuid: str, prefix: str, namespace_name: str) -> dict:
        payload = {
            "id": subnet_uuid,
            "prefix": prefix,
            "status": "Active",
            "namespace": {"name": namespace_name},
        }
        return self.make_api_request("POST", "/api/ipam/prefixes/", payload)

    def associate_subnet_with_network(
        self, network_uuid: str, subnet_uuid: str, role: str
    ):
        url = f"/api/plugins/undercloud-vni/ucvnis/{network_uuid}/"
        payload = {
            "role": {"name": role},
            "relationships": {
                "ucvni_prefixes": {
                    "destination": {
                        "objects": [subnet_uuid],
                    },
                },
            },
        }
        self.make_api_request("PATCH", url, payload)

    def subnet_delete(self, uuid: str) -> dict:
        return self.make_api_request("DELETE", f"/api/ipam/prefixes/{uuid}/")

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
        return self.make_api_request("POST", url, payload)

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
        resp_data = self.make_api_request("POST", url, payload)

        return resp_data["vlan_group_id"]

    def configure_port_status(self, interface_uuid: str, status: str) -> dict:
        url = f"/api/dcim/interfaces/{interface_uuid}/"
        payload = {"status": {"name": status}}
        return self.make_api_request("PATCH", url, payload)

    def fetch_vlan_group_uuid(self, device_uuid: str) -> str:
        url = f"/api/dcim/devices/{device_uuid}/?include=relationships"

        resp_data = self.make_api_request("GET", url)
        try:
            vlan_group_uuid = resp_data["relationships"]["vlan_group_to_devices"][
                "source"
            ]["objects"][0]["id"]
        except (KeyError, IndexError, TypeError) as err:
            raise NautobotNotFoundError(obj="device", ref=device_uuid) from err

        LOG.debug(
            "Device %s belongs to vlan_group_uuid %s", device_uuid, vlan_group_uuid
        )
        return vlan_group_uuid

    def check_vlan_availability(self, interface_id: str | UUID, vlan_tag: int) -> bool:
        """Checks if particular vlan_tag is available in a fabric.

        This method checks if a VLAN number, specified as `vlan_tag`, is used
        in any of the VLAN groups associated with the fabric to which the
        interface, identified by `interface_id`, is connected.
        """
        url = "/api/plugins/undercloud-vni/vlan_availability_check"
        params = {"interface_id": interface_id, "vlan_tag": str(vlan_tag)}

        response = self.make_api_request("GET", url, params=params) or {}
        return response.get("available", False)
