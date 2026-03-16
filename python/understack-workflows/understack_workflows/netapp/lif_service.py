"""Logical Interface (LIF) service layer for NetApp Manager.

This module provides business logic for network interface operations,
including LIF creation, port management, and node identification.
"""

import logging
import re

from understack_workflows.netapp.client import NetAppClientInterface
from understack_workflows.netapp.exceptions import HomeNodeNotFoundError
from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.exceptions import NetworkOperationError
from understack_workflows.netapp.exceptions import SvmNotFoundError
from understack_workflows.netapp.value_objects import InterfaceSpec
from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig
from understack_workflows.netapp.value_objects import NodeResult
from understack_workflows.netapp.value_objects import PortResult
from understack_workflows.netapp.value_objects import PortSpec

logger = logging.getLogger(__name__)


class LifService:
    """Service for managing Logical Interface (LIF) operations with business logic."""

    def __init__(self, client: NetAppClientInterface):
        """Initialize the LIF service.

        Args:
            client: NetApp client for low-level operations
        """
        self._client = client

    def create_lif(self, project_id: str, config: NetappIPInterfaceConfig) -> None:
        """Create a logical interface (LIF) for a project.

        Args:
            project_id: The project identifier
            config: Network interface configuration

        Raises:
            NetworkOperationError: If LIF creation fails
            Exception: If SVM for project is not found
        """
        svm_name = self._get_svm_name(project_id)

        try:
            logger.info(
                "Creating LIF for project %(project_id)s",
                {
                    "project_id": project_id,
                    "svm_name": svm_name,
                    "interface_name": config.name,
                    "address": str(config.address),
                    "vlan_id": config.vlan_id,
                },
            )

            # Verify SVM exists by checking if we can find it
            # This is a business rule - LIF can only be created if SVM exists
            svm_result = self._client.find_svm(svm_name)
            if not svm_result:
                raise SvmNotFoundError(
                    f"SVM '{svm_name}' not found for project '{project_id}'",
                    svm_name=svm_name,
                    context={"project_id": project_id, "interface_name": config.name},
                )

            home_node = self.identify_home_node(config)
            broadcast_domain_name = self._client.get_broadcast_domain_name(
                home_node.name, config.base_port_name
            )

            # Create the home port first
            home_port = self.create_home_port(
                config,
                home_node,
                broadcast_domain_name,
            )

            # Create interface specification
            interface_spec = InterfaceSpec(
                name=config.name,
                address=str(config.address),
                netmask=str(config.network.netmask),
                svm_name=svm_name,
                home_port_uuid=home_port.uuid,
                broadcast_domain_name=broadcast_domain_name,
                service_policy="default-data-nvme-tcp",
            )

            # Create the interface
            result = self._client.get_or_create_ip_interface(interface_spec)

            logger.info(
                "LIF exists for project %(project_id)s",
                {
                    "project_id": project_id,
                    "interface_name": result.name,
                    "uuid": result.uuid,
                    "address": result.address,
                    "svm_name": svm_name,
                },
            )

        except NetAppManagerError:
            raise
        except Exception as e:
            raise NetworkOperationError(
                f"Operation 'LIF creation for project {project_id}' failed: {e}",
                interface_name=config.name,
                context={
                    "project_id": project_id,
                    "svm_name": svm_name,
                    "interface_name": config.name,
                    "address": str(config.address),
                },
            ) from e

    def create_home_port(
        self,
        config: NetappIPInterfaceConfig,
        home_node: NodeResult,
        broadcast_domain_name: str,
    ) -> PortResult:  # pyright: ignore
        """Create a home port for the network interface.

        Args:
            config: Network interface configuration
            home_node: Pre-resolved node that should host the port
            broadcast_domain_name: Pre-resolved broadcast domain name

        Returns:
            PortResult: Result of the port creation

        Raises:
            NetworkOperationError: If port creation fails
            Exception: If home node cannot be identified
        """
        try:
            logger.info(
                "Creating home port for interface %(interface_name)s",
                {
                    "interface_name": config.name,
                    "vlan_id": config.vlan_id,
                    "base_port": config.base_port_name,
                },
            )

            port_spec = PortSpec(
                node_name=home_node.name,
                vlan_id=config.vlan_id,
                base_port_name=config.base_port_name,
                broadcast_domain_name=broadcast_domain_name,
            )

            # Get or create the port
            result = self._client.get_or_create_port(port_spec)

            logger.info(
                "Home port exists for %(interface_name)s on %(node_name)s",
                {
                    "interface_name": config.name,
                    "port_uuid": result.uuid,
                    "port_name": result.name,
                    "node_name": home_node.name,
                },
            )

            return result

        except NetAppManagerError:
            raise
        except Exception as e:
            raise NetworkOperationError(
                f"Operation 'Home port creation for interface {config.name}' "
                f"failed: {e}",
                interface_name=config.name,
                context={
                    "interface_name": config.name,
                    "vlan_id": config.vlan_id,
                    "base_port": config.base_port_name,
                },
            ) from e

    def identify_home_node(self, config: NetappIPInterfaceConfig) -> NodeResult:
        """Identify the home node for a network interface using business logic.

        Args:
            config: Network interface configuration

        Returns:
            NodeResult: The identified home node
        """
        try:
            logger.debug(
                "Identifying home node for interface %(interface_name)s",
                {
                    "interface_name": config.name,
                    "desired_node_number": config.desired_node_number,
                },
            )

            # Get all nodes from the cluster
            nodes = self._client.get_nodes()

            # Apply business logic to find matching node
            for node in nodes:
                # Extract node number from node name using regex
                match = re.search(r"\d+$", node.name)
                if match:
                    node_index = int(match.group())
                    if node_index == config.desired_node_number:
                        logger.debug(
                            "Node %(node_name)s matched desired_node_number of "
                            "%(desired_node_number)d",
                            {
                                "node_name": node.name,
                                "node_index": node_index,
                                "desired_node_number": config.desired_node_number,
                            },
                        )
                        return node

            logger.warning(
                "No node found matching desired_node_number %(desired_node_number)d",
                {
                    "desired_node_number": config.desired_node_number,
                    "interface_name": config.name,
                    "available_nodes": [node.name for node in nodes],
                },
            )

            raise HomeNodeNotFoundError(
                f"Could not find home node for interface {config.name}",
                interface_name=config.name,
                context={
                    "desired_node_number": config.desired_node_number,
                    "vlan_id": config.vlan_id,
                    "available_nodes": [node.name for node in nodes],
                },
            )

        except HomeNodeNotFoundError:
            raise
        except Exception as e:
            raise HomeNodeNotFoundError(
                f"Could not find home node for interface {config.name}: {e}",
                interface_name=config.name,
                context={
                    "desired_node_number": config.desired_node_number,
                    "vlan_id": config.vlan_id,
                    "original_error": str(e),
                },
            ) from e

    def _get_svm_name(self, project_id: str) -> str:
        """Generate SVM name using business naming conventions.

        This is a private method that follows the same naming convention
        as the SvmService to ensure consistency.

        Args:
            project_id: The project identifier

        Returns:
            str: The SVM name following the convention 'os-{project_id}'
        """
        return f"os-{project_id}"
