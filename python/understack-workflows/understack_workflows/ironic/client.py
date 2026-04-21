import logging
from typing import cast

from ironicclient.common.apiclient import exceptions as ironic_exceptions
from ironicclient.v1.client import Client as IronicV1Client
from ironicclient.v1.node import Node
from ironicclient.v1.port import Port
from ironicclient.v1.runbook import Runbook

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

    def set_node_provision_state(
        self,
        node_id: str,
        target: str,
        clean_steps: list[dict] | None = None,
        runbook: str | None = None,
        disable_ramdisk: bool | None = None,
    ) -> None:
        self.client.node.set_provision_state(
            node_id,
            target,
            cleansteps=clean_steps,
            runbook=runbook,
            disable_ramdisk=disable_ramdisk,
        )

    def wait_for_node_provision_state(
        self, node_id: str, expected_state: str, timeout: int = 1800
    ) -> None:
        self.client.node.wait_for_provision_state(
            node_id, expected_state, timeout=timeout
        )

    def set_node_target_raid_config(self, node_id: str, raid_config: dict) -> None:
        self.client.node.set_target_raid_config(node_id, raid_config)

    def get_node_traits(self, node_id: str) -> list[str]:
        return cast(list[str], self.client.node.get_traits(node_id))

    def get_runbook(self, runbook_name_or_id: str) -> Runbook:
        """Get runbook by name or by UUID.

        raises ironicclient.common.apiclient.exceptions.NotFound
        """
        runbook = self.client.runbook.get(runbook_name_or_id)
        # The above raises an error if there was no such runbook.  The following
        # is just to make the type checker happy:
        if not runbook:
            raise ironic_exceptions.NotFound
        return runbook

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
