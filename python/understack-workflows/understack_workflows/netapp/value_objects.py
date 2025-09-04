"""Value objects for NetApp Manager operations.

This module contains immutable dataclasses that represent specifications
and results for NetApp operations. These value objects provide type safety
and clear interfaces for NetApp SDK interactions.
"""

from ipaddress import IPv4Address
from ipaddress import IPv4Network

from pydantic import BaseModel
from pydantic import Field
from pydantic import ConfigDict
from pydantic import computed_field
from pydantic import field_validator


class InterfaceInfo(BaseModel):
    """Information about a network interface from GraphQL response."""

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
    """Network information for a virtual machine from GraphQL response."""

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
    """Configuration for NetApp IP interface creation."""

    name: str = Field(pattern=r'^N\d-lif-(A|B)$')
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
        """Extract side (A or B) from interface name."""
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
        """Get the base port name using the configured NIC slot prefix."""
        return f"{self.nic_slot_prefix}{self.side.lower()}"

    @computed_field
    @property
    def broadcast_domain_name(self) -> str:
        """Get the broadcast domain name based on the side."""
        return f"Fabric-{self.side}"

    @computed_field
    @property
    def route_nexthop(self) -> IPv4Address:
        """Calculate next hop for the static route to reach the clients."""
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
    """Specification for creating a Storage Virtual Machine (SVM)."""

    model_config = ConfigDict(frozen=True)

    name: str
    aggregate_name: str
    language: str = "c.utf_8"
    allowed_protocols: list[str] = ["nvme"]

    @computed_field
    @property
    def root_volume_name(self) -> str:
        """Generate the root volume name for this SVM."""
        return f"{self.name}_root"


class VolumeSpec(BaseModel):
    """Specification for creating a volume."""

    model_config = ConfigDict(frozen=True)

    name: str
    svm_name: str
    aggregate_name: str
    size: str


class InterfaceSpec(BaseModel):
    """Specification for creating a logical interface (LIF)."""

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
        """Get IP configuration as a dictionary for NetApp SDK."""
        return {"address": str(self.address), "netmask": self.netmask}

    @field_validator("address")
    @classmethod
    def validate_ip(cls, v):
        try:
            if isinstance(v, str):
                IPv4Address(v)
        except Exception as e:
            raise ValueError from e
        return v


class PortSpec(BaseModel):
    """Specification for creating a network port."""

    model_config = ConfigDict(frozen=True)

    node_name: str
    vlan_id: int
    base_port_name: str
    broadcast_domain_name: str

    @field_validator("vlan_id")
    @classmethod
    def validate_vlan_id(cls, v):
        if not 1 <= v <= 4094:
            raise ValueError("VLAN ID must be between 1 and 4094")
        return v

    @computed_field
    @property
    def vlan_config(self) -> dict:
        """Get VLAN configuration as a dictionary for NetApp SDK."""
        return {
            "tag": self.vlan_id,
            "base_port": {
                "name": self.base_port_name,
                "node": {"name": self.node_name},
            },
        }


class NamespaceSpec(BaseModel):
    """Specification for querying NVMe namespaces."""

    model_config = ConfigDict(frozen=True)

    svm_name: str
    volume_name: str

    @computed_field
    @property
    def query_string(self) -> str:
        """Generate query string for NetApp SDK namespace collection."""
        return f"svm.name={self.svm_name}&location.volume.name={self.volume_name}"


class RouteSpec(BaseModel):
    """Specification for creating a network route."""

    model_config = ConfigDict(frozen=True)

    svm_name: str
    gateway: str | IPv4Address
    destination: str | IPv4Network

    @field_validator("gateway")
    @classmethod
    def validate_gateway_in_cgn(cls, v):
        """Validate gateway is in carrier-grade NAT range."""
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
        """Convert string to IPv4Network if needed."""
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
    """Result of an SVM operation."""

    model_config = ConfigDict(frozen=True)

    name: str
    uuid: str
    state: str


class VolumeResult(BaseModel):
    """Result of a volume operation."""

    model_config = ConfigDict(frozen=True)

    name: str
    uuid: str
    size: str
    state: str
    svm_name: str | None = None


class NodeResult(BaseModel):
    """Result of a node query operation."""

    model_config = ConfigDict(frozen=True)

    name: str
    uuid: str


class PortResult(BaseModel):
    """Result of a port operation."""

    model_config = ConfigDict(frozen=True)

    uuid: str
    name: str
    node_name: str
    port_type: str | None = None


class InterfaceResult(BaseModel):
    """Result of an interface operation."""

    model_config = ConfigDict(frozen=True)

    name: str
    uuid: str
    address: str | IPv4Address
    netmask: str
    enabled: bool
    svm_name: str | None = None


class NamespaceResult(BaseModel):
    """Result of a namespace query operation."""

    model_config = ConfigDict(frozen=True)

    uuid: str
    name: str
    mapped: bool
    svm_name: str | None = None
    volume_name: str | None = None


class RouteResult(BaseModel):
    """Result of a route creation operation."""

    model_config = ConfigDict(frozen=True)

    uuid: str
    gateway: str
    destination: str | IPv4Network
    svm_name: str
