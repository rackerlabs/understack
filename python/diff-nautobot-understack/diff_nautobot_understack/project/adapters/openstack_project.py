import logging

from diffsync import Adapter

from diff_nautobot_understack.clients.openstack import API
from diff_nautobot_understack.project import models

logger = logging.getLogger(__name__)


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
        self.add(
            self.project(
                id=os_project.id,
                name=os_project.name,
                description=os_project.description,
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
            self.add(
                self.project(
                    id=os_project.id,
                    name=os_project.name,
                    description=os_project.description,
                )
            )
