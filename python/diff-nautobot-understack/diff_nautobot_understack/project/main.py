from pprint import pprint
from diffsync.enum import DiffSyncFlags
from diff_nautobot_understack.project.adapters.openstack_project import Project
from diff_nautobot_understack.project.adapters.nautobot_tenant import Tenant


def openstack_project_diff_from_nautobot_tenant():
    openstack_project = Project()
    openstack_project.load()

    nautobot_tenant = Tenant()
    nautobot_tenant.load()
    openstack_project_destination_tenant_source = openstack_project.diff_from(
        nautobot_tenant, flags=DiffSyncFlags.CONTINUE_ON_FAILURE
    )
    pprint(" Nautobot tenants ⟹ Openstack projects ")
    summary = openstack_project_destination_tenant_source.summary()
    pprint(summary, width=120)
    pprint(openstack_project_destination_tenant_source.dict(), width=120)
