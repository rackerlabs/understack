import uuid

from diffsync import Adapter

from diff_nautobot_understack.clients.nautobot import API
from diff_nautobot_understack.project import models


def _remove_hyphens(tenant_id: str):
    uuid_obj = uuid.UUID(tenant_id)
    return str(uuid_obj.hex)


class Tenant(Adapter):
    project = models.ProjectModel

    top_level = ["project"]
    type = "Tenant"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.api_client = API()
        self.tenant_name = kwargs["name"]

    def load(self):
        url = f"/api/tenancy/tenants/?name={self.tenant_name}&include=relationships"

        tenants_response = self.api_client.make_api_request(url, paginated=True)

        for tenant in tenants_response:
            self.add(
                self.project(
                    id=_remove_hyphens(tenant.get("id")),
                    name=tenant.get("name"),
                    description=tenant.get("description"),
                )
            )
