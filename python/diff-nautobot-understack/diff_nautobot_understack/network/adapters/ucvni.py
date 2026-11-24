from diffsync import Adapter

from diff_nautobot_understack.clients.nautobot import API
from diff_nautobot_understack.network import models


class Network(Adapter):
    """Adapter for Nautobot UCVNIs."""

    network = models.NetworkModel

    top_level = ["network"]
    type = "UCVNI"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_client = API()

    def load(self):
        url = "/api/plugins/undercloud-vni/ucvnis/"
        ucvnis_response = self.api_client.make_api_request(url, paginated=True)

        for ucvni in ucvnis_response:
            ucvni_id = ucvni.get("id")
            if not ucvni_id:
                continue

            # Get tenant ID
            tenant = ucvni.get("tenant", {})
            tenant_id = tenant.get("id") if tenant else None

            self.add(
                self.network(
                    id=ucvni_id,
                    name=ucvni.get("name", ""),
                    tenant_id=tenant_id,
                    ucvni_id=ucvni.get("ucvni_id"),
                )
            )
