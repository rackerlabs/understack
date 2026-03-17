# pyright: reportAttributeAccessIssue=false
# pyright: reportReturnType=false
"""NetApp SDK abstraction layer.

This module provides a thin abstraction layer over the NetApp ONTAP SDK,
handling low-level operations and converting between value objects and SDK objects.
"""

import logging
from abc import ABC
from abc import abstractmethod
from typing import cast

import requests
from netapp_ontap import config
from netapp_ontap.error import NetAppRestError
from netapp_ontap.host_connection import HostConnection
from netapp_ontap.resources import Aggregate
from netapp_ontap.resources import IpInterface
from netapp_ontap.resources import NetworkRoute
from netapp_ontap.resources import Node
from netapp_ontap.resources import NvmeNamespace
from netapp_ontap.resources import Port
from netapp_ontap.resources import Svm
from netapp_ontap.resources import Volume

from understack_workflows.netapp.config import NetAppConfig
from understack_workflows.netapp.exceptions import ConfigurationError
from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.exceptions import NetworkOperationError
from understack_workflows.netapp.exceptions import SvmOperationError
from understack_workflows.netapp.exceptions import VolumeOperationError
from understack_workflows.netapp.value_objects import AggregateResult
from understack_workflows.netapp.value_objects import InterfaceResult
from understack_workflows.netapp.value_objects import InterfaceSpec
from understack_workflows.netapp.value_objects import NamespaceResult
from understack_workflows.netapp.value_objects import NamespaceSpec
from understack_workflows.netapp.value_objects import NodeResult
from understack_workflows.netapp.value_objects import PortResult
from understack_workflows.netapp.value_objects import PortSpec
from understack_workflows.netapp.value_objects import RouteResult
from understack_workflows.netapp.value_objects import RouteSpec
from understack_workflows.netapp.value_objects import SvmResult
from understack_workflows.netapp.value_objects import SvmSpec
from understack_workflows.netapp.value_objects import VolumeResult
from understack_workflows.netapp.value_objects import VolumeSpec

logger = logging.getLogger(__name__)


class NetAppClientInterface(ABC):
    """Abstract interface for NetApp operations."""

    @abstractmethod
    def create_svm(self, svm_spec: SvmSpec) -> SvmResult:
        """Create a Storage Virtual Machine (SVM).

        Args:
            svm_spec: Specification for the SVM to create

        Returns:
            SvmResult: Result of the SVM creation

        Raises:
            SvmOperationError: If SVM creation fails
        """

    @abstractmethod
    def delete_svm(self, svm_name: str) -> bool:
        """Delete a Storage Virtual Machine (SVM).

        Args:
            svm_name: Name of the SVM to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """

    @abstractmethod
    def find_svm(self, svm_name: str) -> SvmResult | None:
        """Find a Storage Virtual Machine (SVM) by name.

        Args:
            svm_name: Name of the SVM to find

        Returns:
            Optional[SvmResult]: SVM result if found, None otherwise
        """

    @abstractmethod
    def create_volume(self, volume_spec: VolumeSpec) -> VolumeResult:
        """Create a volume.

        Args:
            volume_spec: Specification for the volume to create

        Returns:
            VolumeResult: Result of the volume creation

        Raises:
            VolumeOperationError: If volume creation fails
        """

    @abstractmethod
    def delete_volume(self, volume_name: str, force: bool = False) -> bool:
        """Delete a volume.

        Args:
            volume_name: Name of the volume to delete
            force: If True, delete even if volume has dependencies

        Returns:
            bool: True if deletion was successful, False otherwise
        """

    @abstractmethod
    def find_volume(self, volume_name: str, svm_name: str) -> VolumeResult | None:
        """Find a volume by name within a specific SVM.

        Args:
            volume_name: Name of the volume to find
            svm_name: Name of the SVM containing the volume

        Returns:
            Optional[VolumeResult]: Volume result if found, None otherwise
        """

    @abstractmethod
    def get_or_create_ip_interface(
        self, interface_spec: InterfaceSpec
    ) -> InterfaceResult:
        """Get or create a logical interface (LIF).

        Args:
            interface_spec: Specification for the interface to create or load

        Returns:
            InterfaceResult: Result of the interface creation or load

        Raises:
            NetworkOperationError: If interface creation or load fails
        """

    @abstractmethod
    def get_or_create_port(self, port_spec: PortSpec) -> PortResult:
        """Get or create a network port.

        Args:
            port_spec: Specification for the port to create or load

        Returns:
            PortResult: Result of the port creation or load

        Raises:
            NetworkOperationError: If port creation or load fails
        """

    @abstractmethod
    def get_nodes(self) -> list[NodeResult]:
        """Get all nodes in the cluster.

        Returns:
            List[NodeResult]: List of all nodes
        """

    @abstractmethod
    def get_namespaces(self, namespace_spec: NamespaceSpec) -> list[NamespaceResult]:
        """Get NVMe namespaces for a specific SVM and volume.

        Args:
            namespace_spec: Specification for namespace query

        Returns:
            List[NamespaceResult]: List of matching namespaces
        """

    @abstractmethod
    def create_route(self, route_spec: RouteSpec) -> RouteResult:
        """Create a network route.

        Args:
            route_spec: Specification for the route to create

        Returns:
            RouteResult: Result of the route creation

        Raises:
            NetworkOperationError: If route creation fails due to network issues
            NetAppRestError: If NetApp API returns an error during route creation
        """

    @abstractmethod
    def get_aggregates(self) -> list[AggregateResult]:
        """Get aggregate names available on the cluster.

        Returns:
            list[AggregateResult]: Aggregate metadata reported by ONTAP
        """


class NetAppClient(NetAppClientInterface):
    """Concrete implementation of NetApp SDK abstraction layer."""

    def __init__(self, netapp_config: NetAppConfig):
        """Initialize the NetApp client.

        Args:
            netapp_config: NetApp configuration object
        """
        self._config = netapp_config

        # Initialize NetApp SDK connection
        self._setup_connection()

    def _setup_connection(self) -> None:
        """Set up the NetApp SDK connection."""
        try:
            # Only create connection if one doesn't already exist
            # This supports cases where NetAppManager sets up the connection first
            if not hasattr(config, "CONNECTION") or config.CONNECTION is None:
                config.CONNECTION = HostConnection(
                    self._config.hostname,
                    username=self._config.username,
                    password=self._config.password,
                )
                logger.info(
                    "NetApp connection established to %(hostname)s",
                    {"hostname": self._config.hostname},
                )
            else:
                logger.info(
                    "Using existing NetApp connection to %(hostname)s",
                    {"hostname": self._config.hostname},
                )
        except Exception as e:
            raise ConfigurationError(
                f"Configuration error with {self._config.config_path}: {e}",
                config_path=self._config.config_path,
                context={"hostname": self._config.hostname, "original_error": str(e)},
            ) from e

    def create_svm(self, svm_spec: SvmSpec) -> SvmResult:
        """Create a Storage Virtual Machine (SVM)."""
        try:
            logger.info(
                "Creating SVM: %(svm_name)s",
                {"svm_name": svm_spec.name, "aggregate": svm_spec.aggregate_name},
            )

            svm = Svm(
                name=svm_spec.name,
                aggregates=[{"name": svm_spec.aggregate_name}],
                language=svm_spec.language,
                root_volume={
                    "name": svm_spec.root_volume_name,
                    "security_style": "unix",
                },
                allowed_protocols=svm_spec.allowed_protocols,
                nvme={"enabled": True},
            )

            svm.post()
            svm.get()  # Refresh to get the latest state

            result = SvmResult(
                name=str(svm.name),
                uuid=str(svm.uuid),
                state=getattr(svm, "state", "unknown"),
            )

            logger.info(
                "SVM '%(svm_name)s' created successfully",
                {"svm_name": svm_spec.name, "uuid": result.uuid, "state": result.state},
            )

            return result

        except NetAppRestError as e:
            raise SvmOperationError(
                f"NetApp SVM creation failed: {e}",
                svm_name=svm_spec.name,
                context={
                    "svm_name": svm_spec.name,
                    "aggregate": svm_spec.aggregate_name,
                    "netapp_error": str(e),
                },
            ) from e

    def delete_svm(self, svm_name: str) -> bool:
        """Delete a Storage Virtual Machine (SVM)."""
        try:
            logger.info("Deleting SVM: %(svm_name)s", {"svm_name": svm_name})

            svm = Svm()
            svm.get(name=svm_name)

            logger.info(
                "Found SVM '%(svm_name)s' with UUID %(uuid)s",
                {"svm_name": svm_name, "uuid": svm.uuid},
            )

            svm.delete()

            logger.info(
                "SVM '%(svm_name)s' deletion initiated successfully",
                {"svm_name": svm_name},
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to delete SVM '%(svm_name)s': %(error)s",
                {"svm_name": svm_name, "error": str(e)},
            )
            return False

    def find_svm(self, svm_name: str) -> SvmResult | None:
        """Find a Storage Virtual Machine (SVM) by name."""
        try:
            svm = Svm.find(name=svm_name)
            if svm:
                return SvmResult(
                    name=str(svm.name),
                    uuid=str(svm.uuid),
                    state=getattr(svm, "state", "unknown"),
                )
            return None

        except NetAppRestError as e:
            # NetApp SDK raises exception when SVM is not found
            if e.status_code == requests.codes.not_found:
                return None

            raise SvmOperationError(
                f"NetApp SVM lookup failed: {e}",
                svm_name=svm_name,
                context={"svm_name": svm_name, "netapp_error": str(e)},
            ) from e
        except Exception as e:
            raise SvmOperationError(
                f"Unexpected SVM lookup failure: {e}",
                svm_name=svm_name,
                context={"svm_name": svm_name, "original_error": str(e)},
            ) from e

    def create_volume(self, volume_spec: VolumeSpec) -> VolumeResult:
        """Create a volume."""
        try:
            logger.info(
                "Creating volume '%(volume_name)s' with size %(size)s",
                {
                    "volume_name": volume_spec.name,
                    "size": volume_spec.size,
                    "svm": volume_spec.svm_name,
                    "aggregate": volume_spec.aggregate_name,
                },
            )

            volume = Volume(
                name=volume_spec.name,
                svm={"name": volume_spec.svm_name},
                aggregates=[{"name": volume_spec.aggregate_name}],
                size=volume_spec.size,
            )

            volume.post()
            volume.get()  # Refresh to get the latest state

            result = VolumeResult(
                name=str(volume.name),
                uuid=str(volume.uuid),
                size=int(getattr(volume, "size", volume_spec.size)),
                state=getattr(volume, "state", "unknown"),
                svm_name=volume_spec.svm_name,
            )

            logger.info(
                "Volume '%(volume_name)s' created successfully",
                {
                    "volume_name": volume_spec.name,
                    "uuid": result.uuid,
                    "state": result.state,
                },
            )

            return result

        except NetAppRestError as e:
            raise VolumeOperationError(
                f"NetApp Volume creation failed: {e}",
                volume_name=volume_spec.name,
                context={
                    "volume_name": volume_spec.name,
                    "svm_name": volume_spec.svm_name,
                    "aggregate": volume_spec.aggregate_name,
                    "netapp_error": str(e),
                },
            ) from e

    def delete_volume(self, volume_name: str, force: bool = False) -> bool:
        """Delete a volume."""
        try:
            logger.info(
                "Deleting volume: %(volume_name)s",
                {"volume_name": volume_name, "force": force},
            )

            volume = Volume()
            volume.get(name=volume_name)

            logger.info("Found volume '%(volume_name)s'", {"volume_name": volume_name})

            # Check if volume is online and log warning
            if hasattr(volume, "state") and volume.state == "online":
                logger.warning(
                    "Volume '%(volume_name)s' is online", {"volume_name": volume_name}
                )

            if force:
                volume.delete(allow_delete_while_mapped=True)
            else:
                volume.delete()

            logger.info(
                "Volume '%(volume_name)s' deletion initiated successfully",
                {"volume_name": volume_name},
            )
            return True

        except Exception as e:
            logger.warning(
                "Failed to delete volume '%(volume_name)s': %(error)s",
                {"volume_name": volume_name, "force": force, "error": str(e)},
            )
            return False

    def find_volume(self, volume_name: str, svm_name: str) -> VolumeResult | None:
        """Find a volume by name within a specific SVM."""
        try:
            volume = Volume.find(name=volume_name, svm={"name": svm_name})
            if volume:
                return VolumeResult(
                    name=str(volume.name),
                    uuid=str(volume.uuid),
                    size=int(getattr(volume, "size", "unknown")),
                    state=getattr(volume, "state", "unknown"),
                    svm_name=svm_name,
                )
            return None

        except NetAppRestError:
            # NetApp SDK raises exception when volume is not found
            return None
        except Exception as e:
            logger.warning(
                "Error finding volume '%(volume_name)s' in SVM '%(svm_name)s': "
                "%(error)s",
                {"volume_name": volume_name, "svm_name": svm_name, "error": str(e)},
            )
            return None

    def get_or_create_ip_interface(
        self, interface_spec: InterfaceSpec
    ) -> InterfaceResult:
        """Get or create a logical interface (LIF)."""
        try:
            logger.info(
                "Defining IP interface: %(interface_name)s",
                {
                    "interface_name": interface_spec.name,
                    "address": interface_spec.address,
                    "svm": interface_spec.svm_name,
                },
            )

            # attempt to load the existing interface first
            pc = IpInterface.get_collection(
                name=interface_spec.name,
                svm=interface_spec.svm_name,
            )

            try:
                # if we got a interface back then we'll use it
                interface = cast(IpInterface, next(iter(pc)))
            except StopIteration:
                # this happens if there was nothing returned
                # so we'll create a new one
                interface = IpInterface()
                interface.name = interface_spec.name
                interface.ip = interface_spec.ip_info
                interface.enabled = True
                interface.svm = {"name": interface_spec.svm_name}
                interface.location = {
                    "auto_revert": False,
                    "home_port": {"uuid": interface_spec.home_port_uuid},
                    "broadcast_domain": {"name": interface_spec.broadcast_domain_name},
                }
                interface.service_policy = {"name": interface_spec.service_policy}

                logger.debug("Creating IpInterface %s", interface)
                interface.post(hydrate=True)

            result = InterfaceResult(
                name=str(interface.name),
                uuid=str(interface.uuid),
                address=str(interface_spec.address),
                netmask=interface_spec.netmask,
                enabled=True,
                svm_name=interface_spec.svm_name,
            )

            logger.info(
                "IP interface '%(interface_name)s' created successfully",
                {"interface_name": interface_spec.name, "uuid": result.uuid},
            )

            return result

        except NetAppRestError as e:
            raise NetworkOperationError(
                f"NetApp IP interface creation failed: {e}",
                interface_name=interface_spec.name,
                context={
                    "interface_name": interface_spec.name,
                    "svm_name": interface_spec.svm_name,
                    "address": interface_spec.address,
                    "netapp_error": str(e),
                },
            ) from e

    def get_or_create_port(self, port_spec: PortSpec) -> PortResult:
        """Get or create a network port."""
        try:
            logger.info(
                "Defining port on node %(node_name)s",
                {
                    "node_name": port_spec.node_name,
                    "vlan_id": port_spec.vlan_id,
                    "base_port": port_spec.base_port_name,
                },
            )

            # attempt to load the existing port first
            pc = Port.get_collection(
                type="vlan",
                name=f"{port_spec.base_port_name}-{port_spec.vlan_id}",
                fields="uuid,name,enabled,node,vlan",
                **{"node.name": port_spec.node_name},  # pyright: ignore[reportArgumentType]
            )

            try:
                # if we got a port back then we'll use it
                port = cast(Port, next(iter(pc)))
            except StopIteration:
                # this happens if there was nothing returned
                # so we'll create a new one
                port = Port()
                port.type = "vlan"
                port.node = {"name": port_spec.node_name}

                port.enabled = True
                port.broadcast_domain = {
                    "name": port_spec.broadcast_domain_name,
                    "ipspace": {"name": "Default"},
                }
                port.vlan = port_spec.vlan_config

                logger.debug("Creating Port %s", port)
                port.post(hydrate=True)

            result = PortResult(
                uuid=str(port.uuid),
                name=getattr(
                    port, "name", f"{port_spec.base_port_name}-{port_spec.vlan_id}"
                ),
                node_name=port_spec.node_name,
                port_type="vlan",
            )

            logger.info(
                "Port exists on node %(node_name)s",
                {
                    "node_name": port_spec.node_name,
                    "uuid": result.uuid,
                    "name": result.name,
                },
            )

            return result

        except NetAppRestError as e:
            raise NetworkOperationError(
                f"NetApp Port creation failed: {e}",
                context={
                    "node_name": port_spec.node_name,
                    "vlan_id": port_spec.vlan_id,
                    "base_port": port_spec.base_port_name,
                    "netapp_error": str(e),
                },
            ) from e

    def get_nodes(self) -> list[NodeResult]:
        """Get all nodes in the cluster."""
        try:
            logger.debug("Retrieving cluster nodes")

            nodes = list(Node.get_collection())
            results = []

            for node in nodes:
                results.append(NodeResult(name=str(node.name), uuid=str(node.uuid)))

            logger.info(
                "Retrieved %(node_count)d nodes from cluster",
                {"node_count": len(results)},
            )
            return results

        except NetAppRestError as e:
            raise NetAppManagerError(
                f"NetApp Node retrieval failed: {e}",
                context={"netapp_error": str(e)},
            ) from e

    def get_aggregates(self) -> list[AggregateResult]:
        """Get aggregate metadata available on the cluster."""
        try:
            logger.debug("Retrieving cluster aggregates")

            aggregates = list(
                Aggregate.get_collection(
                    fields="name,state,space.block_storage.used_percent"
                )
            )
            results = [
                AggregateResult(
                    name=str(aggregate.name),
                    state=str(aggregate.state)
                    if getattr(aggregate, "state", None) is not None
                    else None,
                    used_percent=getattr(
                        getattr(
                            getattr(aggregate, "space", None), "block_storage", None
                        ),
                        "used_percent",
                        None,
                    ),
                )
                for aggregate in aggregates
                if getattr(aggregate, "name", None)
            ]

            logger.info(
                "Retrieved %(aggregate_count)d aggregates from cluster",
                {"aggregate_count": len(results)},
            )
            return results

        except NetAppRestError as e:
            raise NetAppManagerError(
                f"NetApp Aggregate retrieval failed: {e}",
                context={"netapp_error": str(e)},
            ) from e

    def get_namespaces(self, namespace_spec: NamespaceSpec) -> list[NamespaceResult]:
        """Get NVMe namespaces for a specific SVM and volume."""
        try:
            # Check if connection is available
            if not config.CONNECTION:
                logger.warning("No NetApp connection available for namespace query")
                return []

            logger.debug(
                "Querying namespaces for SVM %(svm_name)s, volume %(volume_name)s",
                {
                    "svm_name": namespace_spec.svm_name,
                    "volume_name": namespace_spec.volume_name,
                },
            )

            ns_collection = NvmeNamespace.get_collection(
                query=namespace_spec.query_string,
                fields="uuid,name,status.mapped",
            )

            results = []
            for ns in ns_collection:
                results.append(
                    NamespaceResult(
                        uuid=str(ns.uuid),
                        name=str(ns.name),
                        mapped=getattr(ns.status, "mapped", False)
                        if hasattr(ns, "status")
                        else False,
                        svm_name=namespace_spec.svm_name,
                        volume_name=namespace_spec.volume_name,
                    )
                )

            logger.info(
                "Retrieved %(namespace_count)d namespaces",
                {
                    "namespace_count": len(results),
                    "svm": namespace_spec.svm_name,
                    "volume": namespace_spec.volume_name,
                },
            )

            return results

        except NetAppRestError as e:
            raise NetAppManagerError(
                f"NetApp Namespace query failed: {e}",
                context={
                    "svm_name": namespace_spec.svm_name,
                    "volume_name": namespace_spec.volume_name,
                    "netapp_error": str(e),
                },
            ) from e

    def create_route(self, route_spec: RouteSpec) -> RouteResult:
        """Create a network route.

        Args:
            route_spec: Specification for the route to create

        Returns:
            RouteResult: Result of the route creation

        Raises:
            NetworkOperationError: If route creation fails due to network issues
            NetAppRestError: If NetApp API returns an error during route creation
        """
        try:
            logger.info(
                "Creating route: %(destination)s via %(gateway)s for SVM %(svm_name)s",
                {
                    "destination": route_spec.destination,
                    "gateway": route_spec.gateway,
                    "svm_name": route_spec.svm_name,
                },
            )

            route = NetworkRoute()
            route.svm = {"name": route_spec.svm_name}
            route.gateway = route_spec.gateway
            route.destination = {
                "address": str(route_spec.destination.network_address),
                "netmask": str(route_spec.destination.netmask),
            }

            logger.debug("Creating NetworkRoute %s", route)
            route.post(hydrate=True)

            result = RouteResult(
                uuid=str(route.uuid),
                gateway=str(route_spec.gateway),
                destination=str(route_spec.destination),
                svm_name=route_spec.svm_name,
            )

            logger.info(
                "Route created successfully: %(destination)s via %(gateway)s",
                {
                    "destination": route_spec.destination,
                    "gateway": route_spec.gateway,
                    "uuid": result.uuid,
                    "svm_name": route_spec.svm_name,
                },
            )

            return result

        except NetAppRestError as e:
            raise NetworkOperationError(
                f"NetApp Route creation failed: {e}",
                context={
                    "svm_name": route_spec.svm_name,
                    "gateway": route_spec.gateway,
                    "destination": route_spec.destination,
                    "netapp_error": str(e),
                },
            ) from e
