import base64
import gzip
import logging
import shutil
import tempfile
from uuid import UUID

from nova.api.metadata import base as instance_metadata
from nova.virt import configdrive
from nova.virt.ironic.driver import IronicDriver

from .argo_client import ArgoClient
from .conf import CONF
from .nautobot_client import NautobotClient

logger = logging.getLogger(__name__)


class IronicUnderstackDriver(IronicDriver):
    capabilities = IronicDriver.capabilities
    rebalances_nodes = IronicDriver.rebalances_nodes

    def __init__(self, virtapi, read_only=False):
        self._nautobot_connection = NautobotClient(
            CONF.nova_understack.nautobot_base_url,
            CONF.nova_understack.nautobot_api_key,
        )

        self._argo_connection = ArgoClient(CONF.nova_understack.argo_api_url, None)

        super().__init__(virtapi, read_only)

    def _get_network_metadata_with_storage(self, node, network_info):
        """Obtain network_metadata to be used in config drive.

        This pulls storage IP information and adds it to the base
        information obtained by original IronicDriver.
        """
        base_metadata = super()._get_network_metadata(node, network_info)
        if not base_metadata:
            return base_metadata

        extra_interfaces = self._nautobot_connection.storage_network_config_for_node(
            UUID(node["uuid"])
        )
        logger.debug("Injecting extra network_info: %s", extra_interfaces)

        for link in extra_interfaces["links"]:
            base_metadata["links"].append(link)
        for network in extra_interfaces["networks"]:
            base_metadata["networks"].append(network)
        return base_metadata

    # This is almost exact copy of the IronicDriver's _generate_configdrive,
    # but we make a determination if injecting storage IPs information is needed
    # based on the instance 'storage' property.
    def _generate_configdrive(
        self, context, instance, node, network_info, extra_md=None, files=None
    ):
        """Generate a config drive with optional storage info.

        :param instance: The instance object.
        :param node: The node object.
        :param network_info: Instance network information.
        :param extra_md: Optional, extra metadata to be added to the
                         configdrive.
        :param files: Optional, a list of paths to files to be added to
                      the configdrive.

        """
        if not extra_md:
            extra_md = {}

        ### Understack modified code START
        if instance.metadata["storage"] == "wanted":
            logger.info("Instance %s requires storage network setup.", instance.uuid)
            project_id = str(UUID(instance.project_id))
            device_id = node["uuid"]
            playbook_args = {"device_id": device_id, "project_id": project_id}
            logger.info(
                "Scheduling ansible run of storage_on_server_create.yml for "
                "device_id=%(device_id)s project_id=%(project_id)s",
                playbook_args,
            )
            result = self._argo_connection.run_playbook(
                "storage_on_server_create.yml", **playbook_args
            )
            logger.debug("Ansible result: %s", result)
            logger.info("Playbook run completed, collecting rest of metadata.")
            network_metadata = self._get_network_metadata_with_storage(
                node, network_info
            )
        else:
            logger.info(
                "Instance %s does not require storage network setup.",
                instance.uuid,
            )
            network_metadata = self._get_network_metadata(node, network_info)
        ### Understack modified code END

        i_meta = instance_metadata.InstanceMetadata(
            instance,
            content=files,
            extra_md=extra_md,
            network_info=network_info,
            network_metadata=network_metadata,
        )

        with tempfile.NamedTemporaryFile() as uncompressed:
            with configdrive.ConfigDriveBuilder(instance_md=i_meta) as cdb:
                cdb.make_drive(uncompressed.name)

            with tempfile.NamedTemporaryFile() as compressed:
                # compress config drive
                with gzip.GzipFile(fileobj=compressed, mode="wb") as gzipped:
                    uncompressed.seek(0)
                    shutil.copyfileobj(uncompressed, gzipped)

                # base64 encode config drive and then decode to utf-8 for JSON
                # serialization
                compressed.seek(0)
                return base64.b64encode(compressed.read()).decode()
