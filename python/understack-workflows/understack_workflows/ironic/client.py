from typing import cast

from ironicclient.common.apiclient import exceptions as ironic_exceptions
from ironicclient.v1.client import Client as IronicV1Client
from ironicclient.v1.node import Node

from understack_workflows.helpers import setup_logger
from understack_workflows.openstack.client import get_ironic_client

logger = setup_logger(__name__)


class IronicClient:
    def __init__(self, cloud: str | None = None) -> None:
        self.client: IronicV1Client = get_ironic_client(cloud=cloud)

    def create_node(self, node_data: dict) -> Node:
        return cast(Node, self.client.node.create(**node_data))

    def list_nodes(self):
        return self.client.node.list()

    def get_node(self, node_ident: str, fields: list[str] | None = None) -> Node:
        return cast(Node, self.client.node.get(node_ident, fields))

    def update_node(self, node_id, patch):
        return self.client.node.update(node_id, patch)

    def create_port(self, port_data: dict):
        return self.client.port.create(**port_data)

    def update_port(self, port_id: str, patch: list):
        return self.client.port.update(port_id, patch)

    def delete_port(self, port_id: str):
        return self.client.port.delete(port_id)

    def list_ports(self, node_id: str):
        return self.client.port.list(node=node_id, detail=True)

    def get_node_inventory(self, node_ident: str) -> dict:
        """Fetch node inventory data from Ironic API.

        Args:
            node_ident: Node UUID, name, or other identifier

        Returns:
            Dict containing node inventory data

        Raises:
            ironic_exceptions.NotFound: If node doesn't exist
            ironic_exceptions.ClientException: For other API errors
        """
        try:
            logger.info("Fetching inventory for node: %s", node_ident)

            # Call the inventory API endpoint
            inventory = self.client.node.get_inventory(node_ident)

            logger.info("Successfully retrieved inventory for node %s", node_ident)
            return inventory

        except ironic_exceptions.NotFound:
            logger.error("Node not found: %s", node_ident)
            raise
        except ironic_exceptions.ClientException as e:
            logger.error("Ironic API error for node %s: %s", node_ident, e)
            raise
        except Exception as e:
            logger.error(
                "Unexpected error fetching inventory for %s: %s", node_ident, e
            )
            raise
