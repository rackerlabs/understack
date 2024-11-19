from functools import cached_property

from flavor_matcher.flavor_spec import FlavorSpec
from novaclient import client as novaclient

from logger import setup_logger

logger = setup_logger(__name__)


class FlavorSynchronizer:
    def __init__(
        self,
        username: str | None = "",
        password: str = "",
        project_id: str | None = None,
        user_domain_id=None,
        auth_url: str | None = None,
    ) -> None:
        self.username = username
        self.password = password
        self.project_id = str(project_id)
        self.user_domain_id = user_domain_id
        self.auth_url = auth_url

    @cached_property
    def _nova(self):
        return novaclient.Client(
            "2",
            self.username,
            self.password,
            self.project_id,
            self.auth_url,
            user_domain_id=self.user_domain_id,
        )

    def reconcile(self, desired_flavors: list[FlavorSpec]):
        existing_flavors = self._nova.flavors.list()
        for flavor in desired_flavors:
            nova_flavor = next(
                (flv for flv in existing_flavors if flv.name == flavor.stripped_name),
                None,
            )

            update_needed = False
            if nova_flavor:
                logger.info(
                    f"Flavor: {flavor.stripped_name} already exists. Syncing values"
                )
                if nova_flavor.ram != flavor.memory_mib:
                    logger.info(
                        f"{flavor.name} RAM mismatch - {nova_flavor.ram=} {flavor.memory_mib=}"
                    )
                    update_needed = True

                if nova_flavor.disk != max(flavor.drives):
                    logger.info(
                        f"{flavor.name} Disk mismatch - {nova_flavor.disk=} {flavor.drives=}"
                    )
                    update_needed = True

                if nova_flavor.vcpus != flavor.cpu_cores:
                    logger.info(
                        f"{flavor.name} CPU mismatch - {nova_flavor.vcpus=} {flavor.cpu_cores=}"
                    )
                    update_needed = True

                if update_needed:
                    logger.debug(
                        f"{flavor.name} is outdated. Deleting so it can be recreated."
                    )
                    nova_flavor.delete()

            else:
                update_needed = True

            if update_needed:
                logger.info(f"Creating {flavor.name}")
                self._create(flavor)

    def _create(self, flavor: FlavorSpec):
        nova_flavor = self._nova.flavors.create(
            flavor.stripped_name,
            flavor.memory_mib,
            flavor.cpu_cores,
            min(flavor.drives),
        )
        nova_flavor.set_keys(
            {
                "resources:DISK_GB": 0,
                "resources:MEMORY_MB": 0,
                "resources:VCPU": 0,
                flavor.baremetal_nova_resource_class: 1,
            }
        )
