"""Logical Interface (LIF) service layer for NetApp Manager.

This module provides business logic for network interface operations,
including LIF creation, port management, and node identification.
"""

import logging
import re

from understack_workflows.netapp.client import NetAppClientInterface
from understack_workflows.netapp.error_handler import ErrorHandler
from understack_workflows.netapp.value_objects import InterfaceSpec
from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig
from understack_workflows.netapp.value_objects import NodeResult
from understack_workflows.netapp.value_objects import PortResult
from understack_workflows.netapp.value_objects import PortSpec


class LifService:
    """Service for managing Logical Interface (LIF) operations with business logic."""

    def __init__(self, client: NetAppClientInterface, error_handler: ErrorHandler):
        """Initialize the LIF service.

        Args:
            client: NetApp client for low-level operations
            error_handler: Error handler for centralized error management
        """
        self._client = client
        self._error_handler = error_handler
        self._logger = logging.getLogger(__name__)

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
            self._error_handler.log_info(
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
                error_msg = f"SVM '{svm_name}' not found for project '{project_id}'"
                self._error_handler.log_warning(
                    error_msg, {"project_id": project_id, "svm_name": svm_name}
                )
                raise Exception("SVM Not Found")

            # Create the home port first
            home_port = self.create_home_port(config)

            # Create interface specification
            interface_spec = InterfaceSpec(
                name=config.name,
                address=str(config.address),
                netmask=str(config.network.netmask),
                svm_name=svm_name,
                home_port_uuid=home_port.uuid,
                broadcast_domain_name=config.broadcast_domain_name,
                service_policy="default-data-nvme-tcp",
            )

            # Create the interface
            result = self._client.get_or_create_ip_interface(interface_spec)

            self._error_handler.log_info(
                "LIF exists for project %(project_id)s",
                {
                    "project_id": project_id,
                    "interface_name": result.name,
                    "uuid": result.uuid,
                    "address": result.address,
                    "svm_name": svm_name,
                },
            )

        except Exception as e:
            if "SVM Not Found" in str(e):
                # Re-raise SVM not found error
                raise e
            else:
                self._error_handler.handle_operation_error(
                    e,
                    f"LIF creation for project {project_id}",
                    {
                        "project_id": project_id,
                        "svm_name": svm_name,
                        "interface_name": config.name,
                        "address": str(config.address),
                    },
                )

    def create_home_port(self, config: NetappIPInterfaceConfig) -> PortResult:  # pyright: ignore
        """Create a home port for the network interface.

        Args:
            config: Network interface configuration

        Returns:
            PortResult: Result of the port creation

        Raises:
            NetworkOperationError: If port creation fails
            Exception: If home node cannot be identified
        """
        try:
            self._error_handler.log_info(
                "Creating home port for interface %(interface_name)s",
                {
                    "interface_name": config.name,
                    "vlan_id": config.vlan_id,
                    "base_port": config.base_port_name,
                    "broadcast_domain": config.broadcast_domain_name,
                },
            )

            # Identify the home node using business logic
            home_node = self.identify_home_node(config)
            if not home_node:
                error_msg = f"Could not find home node for interface {config.name}"
                self._error_handler.log_warning(
                    error_msg, {"interface_name": config.name}
                )
                raise Exception(f"Could not find home node for {config}.")

            # Create port specification
            port_spec = PortSpec(
                node_name=home_node.name,
                vlan_id=config.vlan_id,
                base_port_name=config.base_port_name,
                broadcast_domain_name=config.broadcast_domain_name,
            )

            # Get or create the port
            result = self._client.get_or_create_port(port_spec)

            self._error_handler.log_info(
                "Home port exists.",
                {
                    "interface_name": config.name,
                    "port_uuid": result.uuid,
                    "port_name": result.name,
                    "node_name": home_node.name,
                },
            )

            return result

        except Exception as e:
            if "Could not find home node" in str(e):
                # Re-raise node not found error
                raise e
            else:
                self._error_handler.handle_operation_error(
                    e,
                    f"Home port creation for interface {config.name}",
                    {
                        "interface_name": config.name,
                        "vlan_id": config.vlan_id,
                        "base_port": config.base_port_name,
                    },
                )

    def identify_home_node(self, config: NetappIPInterfaceConfig) -> NodeResult | None:
        """Identify the home node for a network interface using business logic.

        Args:
            config: Network interface configuration

        Returns:
            Optional[NodeResult]: The identified home node, or None if not found
        """
        try:
            self._error_handler.log_debug(
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
                        self._error_handler.log_debug(
                            "Node %(node_name)s matched desired_node_number of "
                            "%(desired_node_number)d",
                            {
                                "node_name": node.name,
                                "node_index": node_index,
                                "desired_node_number": config.desired_node_number,
                            },
                        )
                        return node

            self._error_handler.log_warning(
                "No node found matching desired_node_number %(desired_node_number)d",
                {
                    "desired_node_number": config.desired_node_number,
                    "interface_name": config.name,
                    "available_nodes": [node.name for node in nodes],
                },
            )

            return None

        except Exception as e:
            self._error_handler.log_warning(
                "Error identifying home node for interface %(interface_name)s: "
                "%(error)s",
                {"interface_name": config.name, "error": str(e)},
            )
            return None

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
