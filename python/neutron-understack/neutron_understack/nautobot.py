import inspect
import pathlib
from urllib.parse import urljoin
from uuid import UUID

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
            LOG.error("Nautobot error: %s %s", error, response.content)
            raise NautobotError() from error

    def make_api_request(
        self, url: str, method: str = "get", payload: dict | None = None, params=None
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
        self._log_and_raise_for_status(resp)
        return resp_data

    def post(self, url: str, **payload) -> str:
        result = self.make_api_request(url, "post", payload)
        return result["id"]

    def make_graphql_request(self, query: str, **variables) -> dict:
        url = urljoin(self.base_url, "/api/graphql/")
        payload = {
            "query": query,
            "variables": variables,
        }
        resp = self.s.request("POST", url, timeout=30, json=payload)

        self._log_and_raise_for_status(resp)

        if not resp.content:
            return {"status_code": resp.status_code}

        data = resp.json()

        if "data" not in data:
            LOG.error("Nautobot graphql query failed: %s", data)
            raise NautobotError()

        return data["data"]

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

    def ip_address_create(self, cidr: str, namespace: str) -> str:
        return self.post(
            "/api/ipam/ip-addresses/",
            address=cidr,
            status="Active",
            namespace=namespace,
        )

    def ip_address_delete(self, uuid: str):
        return self.make_api_request(
            f"/api/ipam/ip-addresses/{uuid}/",
            method="delete",
        )

    def interface_create(self, device: str, name: str, type: str = "virtual") -> str:
        return self.post(
            "/api/dcim/interfaces/",
            device=device,
            name=name,
            status="Active",
            type={"value": type},
        )

    def interface_delete(self, uuid: str):
        return self.make_api_request(
            f"/api/dcim/interfaces/{uuid}/",
            method="delete",
        )

    def add_ip_to_interface(self, ip_address_uuid: str, interface_uuid: str):
        return self.post(
            "/api/ipam/ip-address-to-interface/",
            ip_address=ip_address_uuid,
            interface=interface_uuid,
        )

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
        resp_data = self.make_api_request(url, "post", payload)

        return resp_data

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
        response = self.make_api_request(url, "get", params=params)
        if not response:
            return False
        return response.get("available", False)

    def get_switchport_vlan_details(
        self, ucvni_uuid: str, interface_uuid: str
    ) -> tuple[str, int, str]:
        """Get switch device UUID and VLAN ID for a given VNI and Interface."""
        query = """
          query ($ucvni_uuid: String!, $interface_uuid: String!) {
            interfaces(id: [$interface_uuid]) {
              device {
                id
                vlan_group: rel_vlan_group_to_devices {
                  id
                  vlans(cr_ucvni_vlans__source: [$ucvni_uuid]) {
                    vid
                    rel_ucvni_vlans {
                      id
                    }
                  }
                }
              }
            }
          }
        """

        data = self.make_graphql_request(
            query, ucvni_uuid=ucvni_uuid, interface_uuid=interface_uuid
        )
        if not data.get("interfaces"):
            raise ValueError(f"Nautobot missing interface {interface_uuid=}")

        device_data = data["interfaces"][0]["device"]
        switch_uuid = device_data["id"]
        vlan_group_uuid = device_data["vlan_group"]["id"]
        vlans = device_data["vlan_group"]["vlans"]
        if not vlans:
            raise ValueError(f"Nautobot missing vlan {ucvni_uuid=} {interface_uuid=}")

        vlan_id = vlans[0]["vid"]

        return switch_uuid, vlan_id, vlan_group_uuid

    def subnet_cascade_delete(self, uuid: str) -> set[str]:
        """Delete a Prefix, its SVI interfaces and their IP Addresses.

        Nautobot knows which IP Addresses belong to this prefix and will give us
        a list.

        For those IP Addresses associated with one or more SVI interfaces, we
        delete the interfaces and the IP address.

        The Prefix is also deleted.

        Return value is a set of UUIDs for any VLAN Groups containing the
        device(s) that had affected interfaces.
        """
        query = """
          query ($id: String!) {
            prefixes(id: [$id]) {
              ip_addresses {
                id
                interfaces(type__ie: "virtual", name__isw: "vlan") {
                  id
                  device { vlan_group: rel_vlan_group_to_devices { id } }
                }
              }
            }
          }
        """

        vlan_group_uuids = set()

        data = self.make_graphql_request(query, id=uuid)
        prefixes = data.get("prefixes")
        if not prefixes:
            raise ValueError(f"Nautobot has no such prefix {uuid}")

        for ip_address in prefixes[0]["ip_addresses"]:
            interfaces = ip_address["interfaces"]
            if interfaces:
                self.ip_address_delete(ip_address["id"])
            for interface in interfaces:
                self.interface_delete(interface["id"])
                vlan_group_uuids.add(interface["device"]["vlan_group"]["id"])

        self.subnet_delete(uuid)

        return vlan_group_uuids
