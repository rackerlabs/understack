from diffsync import Adapter
from diff_nautobot_understack.clients.openstack import API

from diff_nautobot_understack.project import models


class Project(Adapter):
    project = models.ProjectModel

    top_level = ["project"]
    type = "OpenstackProject"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        openstack_api = API()
        self.cloud = openstack_api.cloud_connection

    def load(self):
        for project in self.cloud.identity.projects():
            self.add(
                self.project(
                    id=project.id,
                    name=project.name,
                    description=project.description,
                )
            )
