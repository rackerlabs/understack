import inspect
from dataclasses import dataclass
from pprint import pformat
from urllib.parse import urljoin
from uuid import UUID

import pynautobot
import requests
from neutron_lib import exceptions as exc
from oslo_log import log

LOG = log.getLogger(__name__)


class NautobotRequestError(exc.NeutronException):
    message = "Nautobot API ERROR %(code)s for %(url)s %(method)s %(payload)s: %(body)s"


class NautobotOSError(exc.NeutronException):
    message = "Error occurred querying Nautobot: %(err)s"


class NautobotNotFoundError(exc.NeutronException):
    message = "%(obj)s not found in Nautobot. ref=%(ref)s"


class NautobotCustomFieldNotFoundError(exc.NeutronException):
    message = "Custom field with name %(cf_name)s not found for %(obj)s"


@dataclass
class VlanPayload:
    id: str
    network_id: str
    vid: int
    vlan_group_name: str
    status: str = "Active"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "vid": self.vid,
            "name": self.id,
            "vlan_group": self.vlan_group_name,
            "status": self.status,
            "relationships": {
                "ucvni_vlans": {"source": {"objects": [{"id": self.network_id}]}}
            },
        }


def _truncated(message: str | bytes, maxlen=200) -> str:
    input = str(message)
    if len(input) <= maxlen:
        return input

    return f"{input[:maxlen]}...{len(input) - maxlen} more chars"


class Nautobot:
    """Basic Nautobot wrapper because pynautobot doesn't expose plugin APIs."""

    def __init__(self, nb_url: str, nb_token: str):
        self.base_url = nb_url
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Token {nb_token}"})
        self.api = pynautobot.api(
            url=nb_url,
            token=nb_token,
        )

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

        if response.content:
            try:
                response_data = response.json()
            except requests.exceptions.JSONDecodeError:
                response_data = {"body": _truncated(response.content)}

        else:
            response_data = {"status_code": response.status_code, "body": ""}

        if response.status_code >= 300:
            response_data = response_data.get("error", response_data)

            raise NautobotRequestError(
                code=response.status_code,
                url=full_url,
                method=method,
                payload=payload,
                body=response_data,
            )

        caller_function = inspect.stack()[1].function
        LOG.debug(
            "[%s] %s %s %s ==> %s",
            caller_function,
            full_url,
            method,
            pformat(payload),
            pformat(response_data),
        )
        return response_data

    def ucvni_create(
        self,
        network_id: str,
        project_id: str,
        ucvni_group: str,
        network_name: str,
        segmentation_id: int,
    ) -> dict:
        payload = {
            "id": network_id,
            "tenant": project_id,
            "name": network_name,
            "ucvni_group": ucvni_group,
            "status": {"name": "Active"},
            "ucvni_id": segmentation_id,
        }

        ucvni: pynautobot.core.response.Record = (
            self.api.plugins.undercloud_vni.ucvnis.create(payload)
        )
        return dict(ucvni)

    def ucvni_delete(self, network_id):
        url = f"/api/plugins/undercloud-vni/ucvnis/{network_id}/"
        return self.make_api_request("DELETE", url)

    def fetch_ucvni(self, network_id: str) -> dict:
        url = f"/api/plugins/undercloud-vni/ucvnis/{network_id}/"
        return self.make_api_request("GET", url)

    def fetch_ucvni_tenant_vlan_id(self, network_id: str) -> int | None:
        ucvni_data = self.fetch_ucvni(network_id=network_id)
        custom_fields = ucvni_data.get("custom_fields", {})
        if "tenant_vlan_id" not in custom_fields:
            raise NautobotCustomFieldNotFoundError(
                cf_name="tenant_vlan_id", obj="UCVNI"
            )
        return custom_fields.get("tenant_vlan_id")

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

    def subnet_create(
        self, subnet_uuid: str, prefix: str, namespace_name: str, tenant_uuid: str
    ) -> dict:
        payload = {
            "id": subnet_uuid,
            "prefix": prefix,
            "status": "Active",
            "namespace": {"name": namespace_name},
            "tenant": {"id": tenant_uuid},
        }
        return self.make_api_request("POST", "/api/ipam/prefixes/", payload)

    def set_svi_role_on_network(self, network_uuid: str, role: str):
        url = f"/api/plugins/undercloud-vni/ucvnis/{network_uuid}/"
        payload = {"role": {"name": role}}
        self.make_api_request("PATCH", url, payload)

    def associate_subnet_with_network(self, network_uuid: str, subnet_uuid: str):
        url = "/api/extras/relationship-associations/"
        payload = {
            "relationship": {"key": "ucvni_prefixes"},
            "source_type": "vni_custom_model.ucvni",
            "source_id": network_uuid,
            "destination_type": "ipam.prefix",
            "destination_id": subnet_uuid,
        }
        self.make_api_request("POST", url, payload)

    def add_tenant_vlan_tag_to_ucvni(self, network_uuid: str, vlan_tag: int) -> dict:
        url = f"/api/plugins/undercloud-vni/ucvnis/{network_uuid}/"
        payload = {"custom_fields": {"tenant_vlan_id": vlan_tag}}
        return self.make_api_request("PATCH", url, payload)

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

    def delete_vlan(self, vlan_id: str):
        return self.api.ipam.vlans.delete([vlan_id])

    def create_vlan_and_associate_vlan_to_ucvni(self, vlan: VlanPayload):
        try:
            result = self.api.ipam.vlans.create(vlan.to_dict())
        except pynautobot.core.query.RequestError as error:
            LOG.error("Nautobot error: %(error)s", {"error": error})
            raise NautobotRequestError(
                code=error.req.status_code,
                url=error.base,
                method="POST",
                payload=error.request_body,
                body=vlan.to_dict(),
            ) from error
        else:
            return result
