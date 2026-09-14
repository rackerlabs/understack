from diffsync import Adapter

from diff_nautobot_understack.clients.nautobot import API
from diff_nautobot_understack.subnet import models


class Prefixes(Adapter):
    """Adapter for Nautobot IPAM prefixes."""

    subnet = models.SubnetModel

    top_level = ["subnet"]
    type = "NautobotPrefix"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_client = API()

    def load(self):
        url = "/api/ipam/prefixes/"
        prefixes_response = self.api_client.make_api_request(url, paginated=True)

        for prefix in prefixes_response:
            # Skip prefixes without a proper UUID (system-generated ones)
            prefix_id = prefix.get("id")
            if not prefix_id:
                continue

            # Get namespace name - this maps to network_id for non-Global
            namespace = prefix.get("namespace", {})
            namespace_name = namespace.get("name") if namespace else None

            # Get tenant ID
            tenant = prefix.get("tenant", {})
            tenant_id = tenant.get("id") if tenant else None

            self.add(
                self.subnet(
                    id=prefix_id,
                    cidr=prefix.get("prefix", ""),
                    network_id=namespace_name or "",
                    tenant_id=tenant_id,
                )
            )
