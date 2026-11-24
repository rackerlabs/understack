from diffsync import Adapter

from diff_nautobot_understack.clients.nautobot import API
from diff_nautobot_understack.device import models


class Devices(Adapter):
    """Adapter for Nautobot devices."""

    device = models.DeviceModel

    top_level = ["device"]
    type = "NautobotDevice"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_client = API()

    def load(self):
        # Filter by role=server to only get baremetal devices
        url = "/api/dcim/devices/?role=server"
        devices_response = self.api_client.make_api_request(url, paginated=True)

        for device in devices_response:
            device_id = device.get("id")
            if not device_id:
                continue

            # Get status name
            status = device.get("status", {})
            status_name = status.get("name") if status else None

            # Get tenant ID
            tenant = device.get("tenant", {})
            tenant_id = tenant.get("id") if tenant else None

            self.add(
                self.device(
                    id=device_id,
                    name=device.get("name"),
                    status=status_name,
                    tenant_id=tenant_id,
                )
            )
