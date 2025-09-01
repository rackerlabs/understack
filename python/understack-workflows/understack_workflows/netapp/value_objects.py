"""Value objects for NetApp Manager operations.

This module contains immutable dataclasses that represent specifications
and results for NetApp operations. These value objects provide type safety
and clear interfaces for NetApp SDK interactions.
"""

import ipaddress
from dataclasses import dataclass
from dataclasses import field
from functools import cached_property
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from understack_workflows.main.netapp_configure_net import VirtualMachineNetworkInfo


@dataclass
class NetappIPInterfaceConfig:
    """Configuration for NetApp IP interface creation."""

    name: str
    address: ipaddress.IPv4Address
    network: ipaddress.IPv4Network
    vlan_id: int
    nic_slot_prefix: str = "e4"

    def netmask_long(self):
        return self.network.netmask

    @cached_property
    def side(self):
        last_character = self.name[-1].upper()
        if last_character in ["A", "B"]:
            return last_character
        raise ValueError("Cannot determine side from interface %s", self.name)

    @cached_property
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
            raise ValueError("Cannot determine node index from name %s", self.name)

    @classmethod
    def from_nautobot_response(
        cls, response: "VirtualMachineNetworkInfo", netapp_config=None
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
            result.append(
                NetappIPInterfaceConfig(
                    name=interface.name,
                    address=ipaddress.IPv4Address(address),
                    network=ipaddress.IPv4Network(interface.address, strict=False),
                    vlan_id=interface.vlan,
                    nic_slot_prefix=nic_slot_prefix,
                )
            )
        return result

    @cached_property
    def base_port_name(self):
        """Get the base port name using the configured NIC slot prefix."""
        return f"{self.nic_slot_prefix}{self.side.lower()}"

    @cached_property
    def broadcast_domain_name(self):
        return f"Fabric-{self.side}"


# Specification Value Objects


@dataclass(frozen=True)
class SvmSpec:
    """Specification for creating a Storage Virtual Machine (SVM)."""

    name: str
    aggregate_name: str
    language: str = "c.utf_8"
    allowed_protocols: list[str] = field(default_factory=lambda: ["nvme"])

    @property
    def root_volume_name(self) -> str:
        """Generate the root volume name for this SVM."""
        return f"{self.name}_root"


@dataclass(frozen=True)
class VolumeSpec:
    """Specification for creating a volume."""

    name: str
    svm_name: str
    aggregate_name: str
    size: str


@dataclass(frozen=True)
class InterfaceSpec:
    """Specification for creating a logical interface (LIF)."""

    name: str
    address: str
    netmask: str
    svm_name: str
    home_port_uuid: str
    broadcast_domain_name: str
    service_policy: str = "default-data-nvme-tcp"

    @property
    def ip_info(self) -> dict:
        """Get IP configuration as a dictionary for NetApp SDK."""
        return {"address": self.address, "netmask": self.netmask}


@dataclass(frozen=True)
class PortSpec:
    """Specification for creating a network port."""

    node_name: str
    vlan_id: int
    base_port_name: str
    broadcast_domain_name: str

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


@dataclass(frozen=True)
class NamespaceSpec:
    """Specification for querying NVMe namespaces."""

    svm_name: str
    volume_name: str

    @property
    def query_string(self) -> str:
        """Generate query string for NetApp SDK namespace collection."""
        return f"svm.name={self.svm_name}&location.volume.name={self.volume_name}"


# Result Value Objects


@dataclass(frozen=True)
class SvmResult:
    """Result of an SVM operation."""

    name: str
    uuid: str
    state: str


@dataclass(frozen=True)
class VolumeResult:
    """Result of a volume operation."""

    name: str
    uuid: str
    size: str
    state: str
    svm_name: str | None = None


@dataclass(frozen=True)
class NodeResult:
    """Result of a node query operation."""

    name: str
    uuid: str


@dataclass(frozen=True)
class PortResult:
    """Result of a port operation."""

    uuid: str
    name: str
    node_name: str
    port_type: str | None = None


@dataclass(frozen=True)
class InterfaceResult:
    """Result of an interface operation."""

    name: str
    uuid: str
    address: str
    netmask: str
    enabled: bool
    svm_name: str | None = None


@dataclass(frozen=True)
class NamespaceResult:
    """Result of a namespace query operation."""

    uuid: str
    name: str
    mapped: bool
    svm_name: str | None = None
    volume_name: str | None = None
