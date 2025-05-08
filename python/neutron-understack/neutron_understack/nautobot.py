from dataclasses import dataclass
from typing import cast

import pynautobot
from neutron_lib import exceptions as exc
from oslo_log import log
from pynautobot.core.response import Record

LOG = log.getLogger(__name__)


class NautobotRequestError(exc.NeutronException):
    message = "Nautobot API ERROR %(code)s for %(url)s %(payload)s: %(body)s"

    @classmethod
    def from_nautobot_request_error(cls, error: pynautobot.RequestError):
        return cls(
            code=error.req.status_code,
            url=error.base,
            payload=error.request_body,
            body=error.args[0],
        )


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
    def __init__(self, nb_url: str, nb_token: str):
        self.api = pynautobot.api(
            url=nb_url,
            token=nb_token,
        )

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

        try:
            ucvni = cast(Record, self.api.plugins.undercloud_vni.ucvnis.create(payload))
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e
        return dict(ucvni)

    def ucvni_delete(self, network_id: str) -> bool:
        try:
            return self.api.plugins.undercloud_vni.ucvnis.delete([network_id])
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def fetch_ucvni_tenant_vlan_id(self, network_id: str) -> int | None:
        try:
            ucvni_raw = self.api.plugins.undercloud_vni.ucvnis.get(network_id)
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e
        if ucvni_raw is None:
            raise NautobotNotFoundError(obj="ucvni", ref=network_id)
        ucvni = cast(Record, ucvni_raw)
        custom_fields = cast(dict, ucvni.custom_fields or {})
        if "tenant_vlan_id" not in custom_fields:
            raise NautobotCustomFieldNotFoundError(
                cf_name="tenant_vlan_id", obj="UCVNI"
            )
        return custom_fields.get("tenant_vlan_id")

    def fetch_namespace_by_name(self, name: str) -> str:
        try:
            ns_raw = self.api.ipam.namespaces.get(name=name)
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e
        if ns_raw is None:
            raise NautobotNotFoundError(obj="namespace", ref=name)
        ns = cast(Record, ns_raw)
        return cast(str, ns.id)

    def namespace_create(self, name: str) -> dict:
        payload = {"name": name}
        try:
            namespace = cast(Record, self.api.ipam.namespaces.create(payload))
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e
        return dict(namespace)

    def namespace_delete(self, namespace_id: str):
        try:
            self.api.ipam.namespaces.delete([namespace_id])
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

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
        try:
            subnet = cast(Record, self.api.ipam.prefixes.create(payload))
            return dict(subnet)
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def set_svi_role_on_network(self, network_uuid: str, role: str) -> bool:
        payload = {"role": {"name": role}}
        try:
            return cast(
                bool,
                self.api.plugins.undercloud_vni.ucvnis.update(
                    id=network_uuid, data=payload
                ),
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def associate_subnet_with_network(
        self, network_uuid: str, subnet_uuid: str
    ) -> Record:
        payload = {
            "relationship": {"key": "ucvni_prefixes"},
            "source_type": "vni_custom_model.ucvni",
            "source_id": network_uuid,
            "destination_type": "ipam.prefix",
            "destination_id": subnet_uuid,
        }
        try:
            return cast(
                Record, self.api.extras.relationship_associations.create(payload)
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def add_tenant_vlan_tag_to_ucvni(self, network_uuid: str, vlan_tag: int) -> bool:
        payload = {"custom_fields": {"tenant_vlan_id": vlan_tag}}
        try:
            return cast(
                bool,
                self.api.plugins.undercloud_vni.ucvnis.update(
                    id=network_uuid, data=payload
                ),
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def subnet_delete(self, uuid: str) -> bool:
        try:
            return self.api.ipam.prefixes.delete([uuid])
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def configure_port_status(self, interface_uuid: str, status: str) -> bool:
        payload = {"status": {"name": status}}
        try:
            return cast(
                bool, self.api.dcim.interfaces.update(id=interface_uuid, data=payload)
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def set_port_vlan_associations(
        self,
        interface_uuid: str,
        native_vlan_id: int | None,
        allowed_vlans_ids: set[int],
        vlan_group_name: str,
    ) -> bool:
        """Set the tagged and untagged vlan(s) on an interface."""
        payload: dict = {
            "mode": "tagged",
            "tagged_vlans": [
                _vlan_payload(vlan_group_name, vlan_id) for vlan_id in allowed_vlans_ids
            ],
        }

        if native_vlan_id is not None:
            payload["untagged_vlan"] = _vlan_payload(vlan_group_name, native_vlan_id)

        try:
            return cast(
                bool, self.api.dcim.interfaces.update(id=interface_uuid, data=payload)
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def add_port_vlan_associations(
        self,
        interface_uuid: str,
        allowed_vlans_ids: set[int],
        vlan_group_name: str,
    ) -> bool:
        """Adds the specified vlan(s) to interface untagged/tagged vlans."""
        try:
            current_state = cast(
                Record | None, self.api.dcim.interfaces.get(interface_uuid)
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e
        if current_state is None:
            raise NautobotNotFoundError(obj="interface", ref=interface_uuid)
        current_tagged_vlans = {
            tagged_vlan.vid for tagged_vlan in current_state.tagged_vlans
        }
        tagged_vlans = current_tagged_vlans.union(allowed_vlans_ids)

        payload = {
            "mode": "tagged",
            "tagged_vlans": [
                _vlan_payload(vlan_group_name, vlan_id) for vlan_id in tagged_vlans
            ],
        }
        try:
            return cast(
                bool, self.api.dcim.interfaces.update(id=interface_uuid, data=payload)
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def remove_port_network_associations(
        self, interface_uuid: str, vlan_ids_to_remove: set[str]
    ) -> bool:
        interface = cast(Record | None, self.api.dcim.interfaces.get(interface_uuid))

        if not interface:
            LOG.error("Interface %s not found in Nautobot", interface_uuid)
            return False

        current = {
            "name": interface.name,
            "untagged_vlan": interface.untagged_vlan,
            "tagged_vlans": interface.tagged_vlans,
        }

        LOG.debug("Nautobot %s query result: %s", interface_uuid, current)
        payload = {}
        if (
            current["untagged_vlan"]
            and current["untagged_vlan"]["id"] in vlan_ids_to_remove
        ):
            payload["untagged_vlan"] = None

        payload["tagged_vlans"] = [
            tagged_vlan["id"]
            for tagged_vlan in current["tagged_vlans"]
            if tagged_vlan["id"] not in vlan_ids_to_remove
        ]
        try:
            return cast(
                bool, self.api.dcim.interfaces.update(id=interface_uuid, data=payload)
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def delete_vlan(self, vlan_id: str) -> bool:
        try:
            return self.api.ipam.vlans.delete([vlan_id])
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def create_vlan_and_associate_vlan_to_ucvni(self, vlan: VlanPayload) -> Record:
        try:
            return cast(Record, self.api.ipam.vlans.create(vlan.to_dict()))
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e

    def get_interface_uuid(self, device_name: str, interface_name: str) -> str:
        device = self.api.dcim.devices.get(name=device_name)
        if not device:
            raise NautobotNotFoundError(obj="device", ref=device_name)

        try:
            interface = self.api.dcim.interfaces.get(
                name=interface_name,
                device=device.id,  # type: ignore
            )
        except pynautobot.RequestError as e:
            raise NautobotRequestError.from_nautobot_request_error(e) from e
        if not interface:
            raise NautobotNotFoundError(obj="interface", ref=interface_name)

        return interface.id  # type: ignore


def _vlan_payload(vlan_group_name: str, vlan_id: int) -> dict:
    return {
        "vlan_group": {"name": vlan_group_name},
        "vid": vlan_id,
    }
