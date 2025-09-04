"""Value objects for NetApp Manager operations.

This module contains immutable Pydantic models that represent specifications
and results for NetApp operations. These value objects provide enhanced type safety,
automatic validation, and clear interfaces for NetApp SDK interactions.

The models leverage Pydantic's built-in validation features including:
- Automatic type conversion and validation
- IP address validation for IPv4Address and IPv4Network fields
- VLAN ID range validation (1-4094)
- Computed fields for derived properties
- Clear validation error messages
"""

from ipaddress import IPv4Address
from ipaddress import IPv4Network

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import computed_field
from pydantic import field_validator


class InterfaceInfo(BaseModel):
    """Information about a network interface from GraphQL response.

    This model provides automatic validation for network interface data
    including VLAN ID range validation and IP address format validation.

    Attributes:
        name: Interface name (e.g., "eth0", "bond0")
        address: IP address in CIDR format (e.g., "192.168.1.10/24")
        vlan: VLAN ID (must be between 1 and 4094)

    Example:
        >>> interface = InterfaceInfo(name="eth0", address="192.168.1.10/24", vlan=100)
        >>> print(interface.name)
        eth0

    Validation errors:
        >>> try:
        ...     InterfaceInfo(name="eth0", address="192.168.1.10/24", vlan=5000)
        ... except ValidationError as e:
        ...     print("VLAN ID out of range")
    """

    model_config = ConfigDict(frozen=True)

    name: str
    address: str
    vlan: int

    @field_validator("vlan")
    @classmethod
    def validate_vlan(cls, v):
        """Validate VLAN ID is in valid range (1-4094)."""
        if not 1 <= v <= 4094:
            raise ValueError("VLAN ID must be between 1 and 4094")
        return v

    @classmethod
    def from_graphql_interface(cls, interface_data: dict) -> "InterfaceInfo":
        """Create InterfaceInfo from GraphQL interface data with validation.

        Args:
            interface_data: GraphQL interface data containing name,
                            ip_addresses, and tagged_vlans

        Returns:
            InterfaceInfo: Validated interface information

        Raises:
            ValueError: If interface has zero or multiple IP addresses or VLANs
        """
        name = interface_data.get("name", "")
        ip_addresses = interface_data.get("ip_addresses", [])
        tagged_vlans = interface_data.get("tagged_vlans", [])

        # Validate exactly one IP address
        if len(ip_addresses) == 0:
            raise ValueError(f"Interface '{name}' has no IP addresses")
        elif len(ip_addresses) > 1:
            raise ValueError(
                f"Interface '{name}' has multiple IP addresses:"
                f" {[ip['address'] for ip in ip_addresses]}"
            )

        # Validate exactly one tagged VLAN
        if len(tagged_vlans) == 0:
            raise ValueError(f"Interface '{name}' has no tagged VLANs")
        elif len(tagged_vlans) > 1:
            raise ValueError(
                f"Interface '{name}' has multiple tagged VLANs:"
                f" {[vlan['vid'] for vlan in tagged_vlans]}"
            )

        address = ip_addresses[0]["address"]
        vlan = tagged_vlans[0]["vid"]

        return cls(name=name, address=address, vlan=vlan)


class VirtualMachineNetworkInfo(BaseModel):
    """Network information for a virtual machine from GraphQL response.

    This model contains a list of validated InterfaceInfo objects,
    providing automatic validation for all network interfaces associated
    with a virtual machine.

    Attributes:
        interfaces: List of InterfaceInfo objects representing network interfaces

    Example:
        >>> vm_info = VirtualMachineNetworkInfo(interfaces=[
        ...     InterfaceInfo(name="eth0", address="192.168.1.10/24", vlan=100)
        ... ])
        >>> print(len(vm_info.interfaces))
        1
    """

    model_config = ConfigDict(frozen=True)

    interfaces: list[InterfaceInfo]

    @classmethod
    def from_graphql_vm(cls, vm_data: dict) -> "VirtualMachineNetworkInfo":
        """Create VirtualMachineNetworkInfo from GraphQL virtual machine data.

        Args:
            vm_data: GraphQL virtual machine data containing interfaces

        Returns:
            VirtualMachineNetworkInfo: Validated virtual machine network information

        Raises:
            ValueError: If any interface validation fails
        """
        interfaces = []
        for interface_data in vm_data.get("interfaces", []):
            interface_info = InterfaceInfo.from_graphql_interface(interface_data)
            interfaces.append(interface_info)

        return cls(interfaces=interfaces)


class NetappIPInterfaceConfig(BaseModel):
    """Configuration for NetApp IP interface creation.

    This model provides comprehensive validation for NetApp interface
    configuration including IP address validation, VLAN ID validation, and
    computed fields for derived properties.

    Attributes:
        name: Interface name following pattern N{1|2}-lif-{A|B} (validated by regex)
        address: IPv4 address for the interface (automatically validated)
        network: IPv4 network in CIDR format (automatically validated)
        vlan_id: VLAN ID (validated to be between 1 and 4094)
        nic_slot_prefix: NIC slot prefix (default: "e4")

    Computed Properties:
        side: Extracts side (A or B) from interface name
        desired_node_number: Extracts node number (1 or 2) from interface name
        base_port_name: Constructs base port name using NIC slot prefix and side
        broadcast_domain_name: Constructs broadcast domain name using side
        route_nexthop: Calculates next hop IP address from network

    Example:
        >>> config = NetappIPInterfaceConfig(
        ...     name="N1-lif-A",
        ...     address="192.168.1.10",
        ...     network="192.168.1.0/24",
        ...     vlan_id=100
        ... )
        >>> print(config.side)  # Computed field
        A
        >>> print(config.base_port_name)  # Computed field
        e4a

    Validation errors:
        >>> try:
        ...     NetappIPInterfaceConfig(
        ...         name="invalid-name",
        ...         address="invalid-ip",
        ...         network="192.168.1.0/24",
        ...         vlan_id=5000
        ...     )
        ... except ValidationError as e:
        ...     print("Multiple validation errors occurred")
    """

    name: str = Field(pattern=r"^N\d-lif-(A|B)$")
    address: IPv4Address
    network: IPv4Network
    vlan_id: int
    nic_slot_prefix: str = "e4"

    @field_validator("vlan_id")
    @classmethod
    def validate_vlan_id(cls, v):
        """Validate VLAN ID is in valid range (1-4094)."""
        if not 1 <= v <= 4094:
            raise ValueError("VLAN ID must be between 1 and 4094")
        return v

    def netmask_long(self):
        return self.network.netmask

    @computed_field
    @property
    def side(self) -> str:
        """Extract side (A or B) from interface name.

        Returns:
            str: Side identifier ("A" or "B")

        Raises:
            ValueError: If interface name doesn't end with A or B
        """
        last_character = self.name[-1].upper()
        if last_character in ["A", "B"]:
            return last_character
        raise ValueError(f"Cannot determine side from interface {self.name}")

    @computed_field
    @property
    def desired_node_number(self) -> int:
        """Node index in the cluster.

        Please note that actual node hostname will be different.
        First node is 1, second is 2 (not zero-indexed).

        Returns:
            int: Node number (1 or 2)

        Raises:
            ValueError: If interface name doesn't start with N1 or N2
        """
        name_part = self.name.split("-")[0]
        if name_part == "N1":
            return 1
        elif name_part == "N2":
            return 2
        else:
            raise ValueError(f"Cannot determine node index from name {self.name}")

    @computed_field
    @property
    def base_port_name(self) -> str:
        """Get the base port name using the configured NIC slot prefix.

        Returns:
            str: Base port name (e.g., "e4a", "e4b")
        """
        return f"{self.nic_slot_prefix}{self.side.lower()}"

    @computed_field
    @property
    def broadcast_domain_name(self) -> str:
        """Get the broadcast domain name based on the side.

        Returns:
            str: Broadcast domain name (e.g., "Fabric-A", "Fabric-B")
        """
        return f"Fabric-{self.side}"

    @computed_field
    @property
    def route_nexthop(self) -> IPv4Address:
        """Calculate next hop for the static route to reach the clients.

        Returns:
            IPv4Address: First host IP address in the network
        """
        return IPv4Address(str(next(self.network.hosts())))

    @classmethod
    def from_nautobot_response(
        cls, response: VirtualMachineNetworkInfo, netapp_config=None
    ):
        """Create NetappIPInterfaceConfig instances from Nautobot response.

        Args:
            response: The Nautobot response containing network interface information
            netapp_config: Optional NetApp configuration to get NIC slot prefix from

        Returns:
            List of NetappIPInterfaceConfig instances
        """
        nic_slot_prefix = "e4"  # Default value
        if netapp_config:
            nic_slot_prefix = netapp_config.netapp_nic_slot_prefix

        result = []
        for interface in response.interfaces:
            address, _ = interface.address.split("/")
            # Create network with strict=False to handle host addresses
            network = IPv4Network(interface.address, strict=False)
            result.append(
                NetappIPInterfaceConfig(
                    name=interface.name,
                    address=address,  # type: ignore[arg-type] # Pydantic will handle IPv4Address conversion
                    network=network,
                    vlan_id=interface.vlan,
                    nic_slot_prefix=nic_slot_prefix,
                )
            )
        return result


# Specification Value Objects


class SvmSpec(BaseModel):
    """Specification for creating a Storage Virtual Machine (SVM).

    This model represents the configuration needed to create
    a NetApp Storage Virtual Machine with automatic validation.

    Attributes:
        name: SVM name (must be unique within the cluster)
        aggregate_name: Name of the aggregate to host the SVM root volume
        language: Language setting for the SVM (default: "c.utf_8")
        allowed_protocols: List of protocols allowed on the SVM (default: ["nvme"])

    Computed Properties:
        root_volume_name: Automatically generated root volume name

    Example:
        >>> svm = SvmSpec(name="test-svm", aggregate_name="aggr1")
        >>> print(svm.root_volume_name)  # Computed field
        test-svm_root
    """

    model_config = ConfigDict(frozen=True)

    name: str
    aggregate_name: str
    language: str = "c.utf_8"
    allowed_protocols: list[str] = ["nvme"]

    @computed_field
    @property
    def root_volume_name(self) -> str:
        """Generate the root volume name for this SVM.

        Returns:
            str: Root volume name in format "{svm_name}_root"
        """
        return f"{self.name}_root"


class VolumeSpec(BaseModel):
    """Specification for creating a volume.

    This model represents the configuration needed to create
    a NetApp volume with automatic validation.

    Attributes:
        name: Volume name (must be unique within the SVM)
        svm_name: Name of the SVM that will contain the volume
        aggregate_name: Name of the aggregate to host the volume
        size: Volume size specification (e.g., "100GB", "1TB")

    Example:
        >>> volume = VolumeSpec(
        ...     name="test-vol",
        ...     svm_name="test-svm",
        ...     aggregate_name="aggr1",
        ...     size="100GB"
        ... )
    """

    model_config = ConfigDict(frozen=True)

    name: str
    svm_name: str
    aggregate_name: str
    size: str


class InterfaceSpec(BaseModel):
    """Specification for creating a logical interface (LIF).

    This model represents the configuration needed to create
    a NetApp Logical Interface with automatic IP address validation.

    Attributes:
        name: Interface name (must be unique within the SVM)
        address: IPv4 address for the interface (automatically validated)
        netmask: Network mask (e.g., "255.255.255.0")
        svm_name: Name of the SVM that will own the interface
        home_port_uuid: UUID of the home port for the interface
        broadcast_domain_name: Name of the broadcast domain
        service_policy: Service policy name (default: "default-data-nvme-tcp")

    Computed Properties:
        ip_info: IP configuration formatted for NetApp SDK

    Example:
        >>> interface = InterfaceSpec(
        ...     name="test-lif",
        ...     address="192.168.1.10",
        ...     netmask="255.255.255.0",
        ...     svm_name="test-svm",
        ...     home_port_uuid="12345678-1234-1234-1234-123456789abc",
        ...     broadcast_domain_name="Default"
        ... )
        >>> print(interface.ip_info)  # Computed field
        {'address': '192.168.1.10', 'netmask': '255.255.255.0'}

    Validation errors:
        >>> try:
        ...     InterfaceSpec(name="test", address="invalid-ip", ...)
        ... except ValidationError as e:
        ...     print("Invalid IP address format")
    """

    model_config = ConfigDict(frozen=True)

    name: str
    address: str | IPv4Address
    netmask: str
    svm_name: str
    home_port_uuid: str
    broadcast_domain_name: str
    service_policy: str = "default-data-nvme-tcp"

    @computed_field
    @property
    def ip_info(self) -> dict:
        """Get IP configuration as a dictionary for NetApp SDK.

        Returns:
            dict: IP configuration with 'address' and 'netmask' keys
        """
        return {"address": str(self.address), "netmask": self.netmask}

    @field_validator("address")
    @classmethod
    def validate_ip(cls, v):
        """Validate IP address format.

        Args:
            v: IP address value to validate

        Returns:
            The validated IP address value

        Raises:
            ValueError: If IP address format is invalid
        """
        try:
            if isinstance(v, str):
                IPv4Address(v)
        except Exception as e:
            raise ValueError from e
        return v


class PortSpec(BaseModel):
    """Specification for creating a network port.

    This model represents the configuration needed to create
    a NetApp network port with automatic VLAN ID validation.

    Attributes:
        node_name: Name of the node that will host the port
        vlan_id: VLAN ID (validated to be between 1 and 4094)
        base_port_name: Base port name (e.g., "e4a", "e4b")
        broadcast_domain_name: Name of the broadcast domain

    Computed Properties:
        vlan_config: VLAN configuration formatted for NetApp SDK

    Example:
        >>> port = PortSpec(
        ...     node_name="node1",
        ...     vlan_id=100,
        ...     base_port_name="e4a",
        ...     broadcast_domain_name="Fabric-A"
        ... )
        >>> print(port.vlan_config)  # Computed field
        {'tag': 100, 'base_port': {'name': 'e4a', 'node': {'name': 'node1'}}}

    Validation errors:
        >>> try:
        ...     PortSpec(node_name="node1", vlan_id=5000, ...)
        ... except ValidationError as e:
        ...     print("VLAN ID out of valid range")
    """

    model_config = ConfigDict(frozen=True)

    node_name: str
    vlan_id: int
    base_port_name: str
    broadcast_domain_name: str

    @field_validator("vlan_id")
    @classmethod
    def validate_vlan_id(cls, v):
        """Validate VLAN ID is in valid range.

        Args:
            v: VLAN ID to validate

        Returns:
            int: Validated VLAN ID

        Raises:
            ValueError: If VLAN ID is not between 1 and 4094
        """
        if not 1 <= v <= 4094:
            raise ValueError("VLAN ID must be between 1 and 4094")
        return v

    @computed_field
    @property
    def vlan_config(self) -> dict:
        """Get VLAN configuration as a dictionary for NetApp SDK.

        Returns:
            dict: VLAN configuration with tag and base_port information
        """
        return {
            "tag": self.vlan_id,
            "base_port": {
                "name": self.base_port_name,
                "node": {"name": self.node_name},
            },
        }


class NamespaceSpec(BaseModel):
    """Specification for querying NVMe namespaces.

    This model represents the parameters needed to query
    NetApp NVMe namespaces.

    Attributes:
        svm_name: Name of the SVM containing the namespace
        volume_name: Name of the volume containing the namespace

    Computed Properties:
        query_string: Query string formatted for NetApp SDK

    Example:
        >>> namespace = NamespaceSpec(svm_name="test-svm", volume_name="test-vol")
        >>> print(namespace.query_string)  # Computed field
        svm.name=test-svm&location.volume.name=test-vol
    """

    model_config = ConfigDict(frozen=True)

    svm_name: str
    volume_name: str

    @computed_field
    @property
    def query_string(self) -> str:
        """Generate query string for NetApp SDK namespace collection.

        Returns:
            str: Query string with SVM and volume name parameters
        """
        return f"svm.name={self.svm_name}&location.volume.name={self.volume_name}"


class RouteSpec(BaseModel):
    """Specification for creating a network route.

    This model represents the configuration needed to create
    a NetApp network route with automatic IP address and network validation.
    The gateway must be within the carrier-grade NAT range (100.64.0.0/10).

    Attributes:
        svm_name: Name of the SVM that will own the route
        gateway: Gateway IP address (must be in 100.64.0.0/10 range)
        destination: Destination network in CIDR format

    Example:
        >>> route = RouteSpec(
        ...     svm_name="test-svm",
        ...     gateway="100.64.1.1",
        ...     destination="100.126.0.0/17"
        ... )

    Validation errors:
        >>> try:
        ...     RouteSpec(
        ...         svm_name="test-svm",
        ...         gateway="192.168.1.1",  # Not in CGN range
        ...         destination="100.126.0.0/17"
        ...     )
        ... except ValidationError as e:
        ...     print("Gateway not in carrier-grade NAT range")
    """

    model_config = ConfigDict(frozen=True)

    svm_name: str
    gateway: str | IPv4Address
    destination: str | IPv4Network

    @field_validator("gateway")
    @classmethod
    def validate_gateway_in_cgn(cls, v):
        """Validate gateway is in carrier-grade NAT range.

        Args:
            v: Gateway IP address to validate

        Returns:
            IPv4Address: Validated gateway IP address

        Raises:
            ValueError: If gateway is not in 100.64.0.0/10 subnet or invalid format
        """
        try:
            if isinstance(v, str):
                v = IPv4Address(v)
            cgn_network = IPv4Network("100.64.0.0/10")
            if v not in cgn_network:
                raise ValueError(f"Gateway {v} must be within 100.64.0.0/10 subnet")
            return v
        except Exception as e:
            raise ValueError(f"Invalid gateway address: {e}") from e

    @field_validator("destination")
    @classmethod
    def validate_destination(cls, v):
        """Convert string to IPv4Network if needed.

        Args:
            v: Destination network to validate

        Returns:
            IPv4Network: Validated destination network

        Raises:
            ValueError: If destination network format is invalid
        """
        try:
            if isinstance(v, str):
                return IPv4Network(v)
            return v
        except Exception as e:
            raise ValueError(f"Invalid destination network: {e}") from e

    @classmethod
    def from_nexthop_ip(cls, svm_name: str, nexthop_ip: str) -> "RouteSpec":
        """Create RouteSpec from nexthop IP with calculated destination.

        Args:
            svm_name: Name of the Storage Virtual Machine
            nexthop_ip: IP address of the route gateway/nexthop

        Returns:
            RouteSpec: Route specification with calculated destination

        Raises:
            ValueError: If IP pattern is not supported for route destination calculation
        """
        destination = cls._calculate_destination(nexthop_ip)
        return cls(
            svm_name=svm_name,
            gateway=nexthop_ip,
            destination=destination,
        )

    @staticmethod
    def _calculate_destination(nexthop_ip: str) -> IPv4Network:
        """Calculate route destination based on IP address pattern.

        Args:
            nexthop_ip: IP address to analyze for destination calculation

        Returns:
            IPv4Network: Route destination in CIDR format

        Raises:
            ValueError: If IP is not in 100.64.0.0/10 subnet or third octet not 0 or 128
        """
        ip = IPv4Address(nexthop_ip)

        # Validate that IP is within 100.64.0.0/10 subnet
        carrier_grade_nat_network = IPv4Network("100.64.0.0/10")
        if ip not in carrier_grade_nat_network:
            raise ValueError(
                f"IP address {nexthop_ip} is not within required 100.64.0.0/10 subnet"
            )

        third_octet = int(str(ip).split(".")[2])

        if third_octet == 0:
            return IPv4Network("100.126.0.0/17")
        elif third_octet == 128:
            return IPv4Network("100.126.128.0/17")
        else:
            raise ValueError(
                f"Unsupported IP pattern for route destination: {nexthop_ip}"
            )


# Result Value Objects


class SvmResult(BaseModel):
    """Result of an SVM operation.

    This model represents the result returned from NetApp SDK
    after creating or querying a Storage Virtual Machine.

    Attributes:
        name: SVM name
        uuid: Unique identifier assigned by NetApp
        state: Current state of the SVM (e.g., "running", "stopped")

    Example:
        >>> result = SvmResult(
        ...     name="test-svm",
        ...     uuid="12345678-1234-1234-1234-123456789abc",
        ...     state="running"
        ... )
    """

    model_config = ConfigDict(frozen=True)

    name: str
    uuid: str
    state: str


class VolumeResult(BaseModel):
    """Result of a volume operation.

    This model represents the result returned from NetApp SDK
    after creating or querying a volume.

    Attributes:
        name: Volume name
        uuid: Unique identifier assigned by NetApp
        size: Volume size (e.g., "100GB")
        state: Current state of the volume (e.g., "online", "offline")
        svm_name: Name of the SVM containing the volume (optional)

    Example:
        >>> result = VolumeResult(
        ...     name="test-vol",
        ...     uuid="12345678-1234-1234-1234-123456789abc",
        ...     size="100GB",
        ...     state="online",
        ...     svm_name="test-svm"
        ... )
    """

    model_config = ConfigDict(frozen=True)

    name: str
    uuid: str
    size: str
    state: str
    svm_name: str | None = None


class NodeResult(BaseModel):
    """Result of a node query operation.

    This model represents the result returned from NetApp SDK
    after querying cluster nodes.

    Attributes:
        name: Node name
        uuid: Unique identifier assigned by NetApp

    Example:
        >>> result = NodeResult(
        ...     name="node1",
        ...     uuid="12345678-1234-1234-1234-123456789abc"
        ... )
    """

    model_config = ConfigDict(frozen=True)

    name: str
    uuid: str


class PortResult(BaseModel):
    """Result of a port operation.

    This model represents the result returned from NetApp SDK
    after creating or querying a network port.

    Attributes:
        uuid: Unique identifier assigned by NetApp
        name: Port name (e.g., "e4a-100")
        node_name: Name of the node hosting the port
        port_type: Type of port (optional, e.g., "vlan", "physical")

    Example:
        >>> result = PortResult(
        ...     uuid="12345678-1234-1234-1234-123456789abc",
        ...     name="e4a-100",
        ...     node_name="node1",
        ...     port_type="vlan"
        ... )
    """

    model_config = ConfigDict(frozen=True)

    uuid: str
    name: str
    node_name: str
    port_type: str | None = None


class InterfaceResult(BaseModel):
    """Result of an interface operation.

    This model represents the result returned from NetApp SDK
    after creating or querying a logical interface (LIF).

    Attributes:
        name: Interface name
        uuid: Unique identifier assigned by NetApp
        address: IP address of the interface (automatically validated)
        netmask: Network mask
        enabled: Whether the interface is enabled
        svm_name: Name of the SVM owning the interface (optional)

    Example:
        >>> result = InterfaceResult(
        ...     name="test-lif",
        ...     uuid="12345678-1234-1234-1234-123456789abc",
        ...     address="192.168.1.10",
        ...     netmask="255.255.255.0",
        ...     enabled=True,
        ...     svm_name="test-svm"
        ... )
    """

    model_config = ConfigDict(frozen=True)

    name: str
    uuid: str
    address: str | IPv4Address
    netmask: str
    enabled: bool
    svm_name: str | None = None


class NamespaceResult(BaseModel):
    """Result of a namespace query operation.

    This model represents the result returned from NetApp SDK
    after querying NVMe namespaces.

    Attributes:
        uuid: Unique identifier assigned by NetApp
        name: Namespace name
        mapped: Whether the namespace is mapped to a host
        svm_name: Name of the SVM containing the namespace (optional)
        volume_name: Name of the volume containing the namespace (optional)

    Example:
        >>> result = NamespaceResult(
        ...     uuid="12345678-1234-1234-1234-123456789abc",
        ...     name="test-namespace",
        ...     mapped=True,
        ...     svm_name="test-svm",
        ...     volume_name="test-vol"
        ... )
    """

    model_config = ConfigDict(frozen=True)

    uuid: str
    name: str
    mapped: bool
    svm_name: str | None = None
    volume_name: str | None = None


class RouteResult(BaseModel):
    """Result of a route creation operation.

    This model represents the result returned from NetApp SDK
    after creating a network route.

    Attributes:
        uuid: Unique identifier assigned by NetApp
        gateway: Gateway IP address
        destination: Destination network (automatically validated)
        svm_name: Name of the SVM owning the route

    Example:
        >>> result = RouteResult(
        ...     uuid="12345678-1234-1234-1234-123456789abc",
        ...     gateway="100.64.1.1",
        ...     destination="100.126.0.0/17",
        ...     svm_name="test-svm"
        ... )
    """

    model_config = ConfigDict(frozen=True)

    uuid: str
    gateway: str
    destination: str | IPv4Network
    svm_name: str
