"""Route service layer for NetApp Manager.

This module provides business logic for network route operations,
including route creation and nexthop management.
"""

import logging

from understack_workflows.netapp.client import NetAppClientInterface
from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.exceptions import NetworkOperationError
from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig
from understack_workflows.netapp.value_objects import RouteResult
from understack_workflows.netapp.value_objects import RouteSpec

logger = logging.getLogger(__name__)


class RouteService:
    """Service for managing network route operations with business logic."""

    def __init__(self, client: NetAppClientInterface):
        """Initialize the route service.

        Args:
            client: NetApp client for low-level operations
        """
        self._client = client

    def create_routes_from_interfaces(
        self,
        project_id: str,
        interface_configs: list[NetappIPInterfaceConfig],
    ) -> list[RouteResult]:  # pyright: ignore
        """Create routes based on interface configurations.

        Args:
            project_id: The project identifier
            interface_configs: List of network interface configurations

        Returns:
            list[RouteResult]: List of created route results

        Raises:
            NetworkOperationError: If route creation fails
        """
        try:
            # Extract unique nexthop addresses
            unique_nexthops = self._extract_unique_nexthops(interface_configs)

            logger.debug(
                "Found %(count)d unique nexthop addresses for project %(project_id)s",
                {"count": len(unique_nexthops), "project_id": project_id},
            )

            # Create routes for each unique nexthop
            svm_name = f"os-{project_id}"
            results = []

            for nexthop in unique_nexthops:
                try:
                    route_spec = RouteSpec.from_nexthop_ip(svm_name, nexthop)
                    result = self._client.create_route(route_spec)
                    results.append(result)

                    logger.info(
                        "Created route: %(destination)s via %(gateway)s for SVM "
                        "%(svm_name)s",
                        {
                            "destination": result.destination,
                            "gateway": result.gateway,
                            "svm_name": result.svm_name,
                        },
                    )

                except NetAppManagerError:
                    raise
                except Exception as e:
                    raise NetworkOperationError(
                        f"Operation 'Route creation for nexthop {nexthop}' failed: {e}",
                        context={
                            "project_id": project_id,
                            "svm_name": svm_name,
                            "nexthop": nexthop,
                        },
                    ) from e

            return results

        except NetAppManagerError:
            raise
        except Exception as e:
            raise NetworkOperationError(
                f"Operation 'Route creation for project {project_id}' failed: {e}",
                context={
                    "project_id": project_id,
                    "interface_count": len(interface_configs),
                },
            ) from e

    def _extract_unique_nexthops(
        self, interface_configs: list[NetappIPInterfaceConfig]
    ) -> list[str]:
        """Extract unique nexthop IP addresses from interface configurations.

        Args:
            interface_configs: List of network interface configurations

        Returns:
            list[str]: List of unique nexthop IP addresses
        """
        nexthops = [str(config.route_nexthop) for config in interface_configs]
        unique_nexthops = list(set(nexthops))  # Remove duplicates

        logger.debug(
            "Extracted %(unique_count)d unique nexthops from %(total_count)d "
            "interfaces",
            {
                "unique_count": len(unique_nexthops),
                "total_count": len(interface_configs),
                "nexthops": unique_nexthops,
            },
        )

        return unique_nexthops
