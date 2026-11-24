from diffsync import Adapter

from diff_nautobot_understack.clients.openstack import API
from diff_nautobot_understack.network import models


class Network(Adapter):
    network = models.NetworkModel

    top_level = ["network"]
    type = "OpenstackNetwork"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        openstack_api = API()
        self.cloud = openstack_api.cloud_connection

    def load(self):
        for network in self.cloud.network.networks():
            self.add(
                self.network(
                    id=network.id,
                    name=network.name,
                    tenant_id=network.project_id,
                    ucvni_id=network.provider_segmentation_id,
                )
            )
