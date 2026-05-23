import logging

from diffsync import Adapter

from diff_nautobot_understack.clients.openstack import API
from diff_nautobot_understack.project import models

logger = logging.getLogger(__name__)


def _get_tenant_name(cloud, project) -> str:
    """Generate tenant name as domain:project_name to match sync logic."""
    domain_id = project.domain_id

    if domain_id == "default":
        domain_name = "default"
    elif domain_id:
        domain = cloud.identity.get_domain(domain_id)
        domain_name = domain.name if domain else "unknown"
    else:
        domain_name = "unknown"

    return f"{domain_name}:{project.name}"


class Project(Adapter):
    project = models.ProjectModel

    top_level = ["project"]
    type = "OpenstackProject"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        openstack_api = API()
        self.project_name = kwargs["name"]
        self.cloud = openstack_api.cloud_connection

    def load(self):
        os_project = self.cloud.get_project(name_or_id=self.project_name)
        if not os_project:
            logger.error(f"Project '{self.project_name}' not found.")
            return

        # Skip domains - they are not synced to Nautobot
        if getattr(os_project, "is_domain", False):
            logger.debug(f"Skipping domain '{self.project_name}'")
            return

        tenant_name = _get_tenant_name(self.cloud, os_project)
        self.add(
            self.project(
                id=os_project.id,
                name=tenant_name,
                description=os_project.description or "",
            )
        )


class Projects(Adapter):
    project = models.ProjectModel

    top_level = ["project"]
    type = "OpenstackProject"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        openstack_api = API()
        self.cloud = openstack_api.cloud_connection

    def load(self):
        for os_project in self.cloud.identity.projects():
            # Skip domains - they are not synced to Nautobot
            if getattr(os_project, "is_domain", False):
                logger.debug(f"Skipping domain '{os_project.name}'")
                continue

            tenant_name = _get_tenant_name(self.cloud, os_project)
            self.add(
                self.project(
                    id=os_project.id,
                    name=tenant_name,
                    description=os_project.description or "",
                )
            )
