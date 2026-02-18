import logging
from typing import cast

from ironicclient.common.apiclient import exceptions as ironic_exceptions
from ironicclient.v1.client import Client as IronicV1Client
from ironicclient.v1.node import Node
from ironicclient.v1.port import Port

from understack_workflows.openstack.client import get_ironic_client

logger = logging.getLogger(__name__)


class IronicClient:
    def __init__(self, cloud: str | None = None) -> None:
        """Initialize our ironicclient wrapper."""
        self.client: IronicV1Client = get_ironic_client(cloud=cloud)
        self.logged_in = True

    def create_node(self, node_data: dict) -> Node:
        return cast(Node, self.client.node.create(**node_data))

    def list_nodes(self):
        return self.client.node.list()

    def get_node(self, node_ident: str, fields: list[str] | None = None) -> Node:
        return cast(Node, self.client.node.get(node_ident, fields))

    def update_node(self, node_id, patch):
        return self.client.node.update(node_id, patch)

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

    def create_port(self, port_data: dict) -> Port:
        return cast(Port, self.client.port.create(**port_data))

    def get_port(self, port_ident: str, fields: list[str] | None = None) -> Port:
        """Get a specific port by UUID or address.

        Args:
            port_ident: Port UUID or MAC address
            fields: Optional list of fields to return

        Returns:
            Port object

        Raises:
            ironic_exceptions.NotFound: If port doesn't exist
            ironic_exceptions.ClientException: For other API errors
        """
        try:
            logger.debug("Fetching port: %s", port_ident)
            port = self.client.port.get(port_ident, fields)
            logger.debug("Successfully retrieved port %s", port_ident)
            return cast(Port, port)
        except ironic_exceptions.NotFound:
            logger.error("Port not found: %s", port_ident)
            raise
        except ironic_exceptions.ClientException as e:
            logger.error("Ironic API error for port %s: %s", port_ident, e)
            raise

    def update_port(self, port_id: str, patch: list):
        return self.client.port.update(port_id, patch)

    def delete_port(self, port_id: str):
        return self.client.port.delete(port_id)

    def list_ports(self, node_id: str):
        return self.client.port.list(node=node_id, detail=True)
