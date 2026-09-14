from diffsync import Adapter

from diff_nautobot_understack.clients.openstack import API
from diff_nautobot_understack.device import models

# Map Ironic provision states to Nautobot statuses
PROVISION_STATE_MAP = {
    "active": "Active",
    "enroll": "Planned",
    "available": "Available",
    "deploy failed": "Quarantine",
    "error": "Quarantine",
    "rescue": "Quarantine",
    "rescue failed": "Quarantine",
    "unrescueing": "Quarantine",
    "manageable": "Staged",
    "inspecting": "Provisioning",
    "deploying": "Provisioning",
    "cleaning": "Quarantine",
    "clean failed": "Quarantine",
    "deleting": "Decommissioning",
}


class Nodes(Adapter):
    """Adapter for Ironic baremetal nodes."""

    device = models.DeviceModel

    top_level = ["device"]
    type = "IronicNode"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        openstack_api = API()
        self.cloud = openstack_api.cloud_connection

    def load(self):
        for node in self.cloud.baremetal.nodes():
            # Map provision state to Nautobot status
            status = PROVISION_STATE_MAP.get(node.provision_state)

            self.add(
                self.device(
                    id=node.id,
                    name=node.name,
                    status=status,
                    tenant_id=node.lessee,
                )
            )
