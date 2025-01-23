from diffsync import Adapter
from pydantic import BaseModel
from diff_nautobot_understack.clients.nautobot import API

from diff_nautobot_understack.network import models


class UcvniDetails(BaseModel):
    id: str
    name: str
    status: str
    ucvni_id: int
    ucvni_group: str
    vlan_group: str
    vlan_id: int


class NautobotError(Exception):
    message = "Nautobot error"


class Network(Adapter):
    CALLER_FRAME = 1
    network = models.NetworkModel

    top_level = ["network"]
    type = "UCVNI"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_client = API()

    def load(self):
        ucvni_data: list[UcvniDetails] = self.ucvni_get()
        for ucvni_item in ucvni_data:
            network = self.network(
                id=ucvni_item.id,
                name=ucvni_item.name,
                vni_id=ucvni_item.vlan_id,
                provider_physical_network=ucvni_item.vlan_group,
                status=ucvni_item.status,
            )
            self.add(network)

    def ucvni_get(
        self,
    ) -> list[UcvniDetails]:
        ucvni_detail_list: list[UcvniDetails] = []

        url = "/api/plugins/undercloud-vni/ucvnis/?include=relationship"

        ucvnis_response = self.api_client.make_api_request(
            f"{url}/?include=relationships", paginated=True
        )

        for ucvni_item in ucvnis_response:
            ucvni_group = self.api_client.make_api_request(
                url=ucvni_item.get("ucvni_group", {}).get("url")
            )
            status = self.api_client.make_api_request(
                url=ucvni_item.get("status", {}).get("url")
            )
            vlan_uuid_objects = (
                ucvni_item.get("relationships", {})
                .get("ucvni_vlans", {})
                .get("destination")
                .get("objects")
            )
            vlan_details = self.get_vlan_details(vlan_uuid_objects)
            vlan_group, vlan_ids = next(iter(vlan_details.items()))
            ucvni_details = UcvniDetails(
                id=ucvni_item.get("id"),
                name=ucvni_item.get("name"),
                ucvni_id=ucvni_item.get("ucvni_id"),
                ucvni_group=ucvni_group.get("name"),
                status=status.get("name").lower(),
                vlan_group=vlan_group,
                vlan_id=int(vlan_ids[0]),
            )
            ucvni_detail_list.append(ucvni_details)
        return ucvni_detail_list

    def get_vlan_details(self, vlan_uuid_objects):
        vlan_uuids = [vlan_uuid_object["id"] for vlan_uuid_object in vlan_uuid_objects]
        vlan_details = {}

        vlan_uuids_query_params = "&".join(f"id={value}" for value in vlan_uuids)
        vlan_url = f"/api/ipam/vlans/?{vlan_uuids_query_params}"

        vlans_response = self.api_client.make_api_request(url=vlan_url, paginated=True)

        for vlan_response in vlans_response:
            vlan_group_url = vlan_response.get("vlan_group", {}).get("url")

            if vlan_group_url:
                vlan_group_response = self.api_client.make_api_request(
                    url=vlan_group_url
                )
                vlan_group_name = vlan_group_response.get("name")
                vlan_id = vlan_response.get("vid")

                if vlan_group_name:
                    vlan_details.setdefault(vlan_group_name, []).append(vlan_id)

        return vlan_details
