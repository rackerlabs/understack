from diffsync import Adapter

from diff_nautobot_understack.clients.openstack import API
from diff_nautobot_understack.subnet import models


class Subnets(Adapter):
    """Adapter for OpenStack Neutron subnets."""

    subnet = models.SubnetModel

    top_level = ["subnet"]
    type = "OpenstackSubnet"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        openstack_api = API()
        self.cloud = openstack_api.cloud_connection

    def load(self):
        for subnet in self.cloud.network.subnets():
            self.add(
                self.subnet(
                    id=subnet.id,
                    cidr=subnet.cidr,
                    network_id=subnet.network_id,
                    tenant_id=subnet.project_id,
                )
            )
