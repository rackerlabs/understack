import logging
from uuid import UUID

from nova.virt.ironic.driver import IronicDriver

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

        super().__init__(virtapi, read_only)

    def _get_network_metadata(self, node, network_info):
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

        for link in extra_interfaces["links"]:
            base_metadata["links"].append(link)
        for network in extra_interfaces["networks"]:
            base_metadata["networks"].append(network)
        return base_metadata
