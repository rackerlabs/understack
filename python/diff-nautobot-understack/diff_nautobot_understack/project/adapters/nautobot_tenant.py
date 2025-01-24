from diffsync import Adapter
from diff_nautobot_understack.clients.nautobot import API

from diff_nautobot_understack.project import models


class Tenant(Adapter):
    project = models.ProjectModel

    top_level = ["project"]
    type = "Tenant"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_client = API()

    def load(self):
        url = "/api/tenancy/tenants/?include=relationships"

        tenants_response = self.api_client.make_api_request(url, paginated=True)

        for tenant in tenants_response:
            self.add(
                self.project(
                    id=tenant.get("id"),
                    name=tenant.get("name"),
                    description=tenant.get("description"),
                )
            )
