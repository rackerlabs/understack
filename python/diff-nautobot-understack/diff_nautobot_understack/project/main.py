from diffsync.diff import Diff
from diffsync.enum import DiffSyncFlags

from diff_nautobot_understack.project.adapters.nautobot_tenant import Tenant
from diff_nautobot_understack.project.adapters.openstack_project import Project
from diff_nautobot_understack.settings import app_settings as settings


def openstack_project_diff_from_nautobot_tenant(os_project=None) -> Diff:
    project_name = os_project if os_project is not None else settings.os_project
    openstack_project = Project(name=project_name)
    openstack_project.load()

    nautobot_tenant = Tenant(name=project_name)
    nautobot_tenant.load()
    tenant_destination_openstack_project_source = nautobot_tenant.diff_from(
        openstack_project, flags=DiffSyncFlags.CONTINUE_ON_FAILURE
    )
    return tenant_destination_openstack_project_source
