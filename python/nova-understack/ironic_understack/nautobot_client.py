import ipaddress
import uuid
from dataclasses import dataclass
from uuid import UUID

import requests


@dataclass
class IPAddress:
    """Represents an IP address from Nautobot."""

    interface: ipaddress.IPv4Interface | ipaddress.IPv6Interface

    @classmethod
    def from_address_string(cls, address: str) -> "IPAddress":
        """Create IPAddress from address string with CIDR notation."""
        try:
            # Try to parse as interface (with prefix)
            interface = ipaddress.ip_interface(address)
            return cls(interface=interface)
        except ipaddress.AddressValueError as e:
            raise ValueError(f"Invalid IP address format: {address}") from e

    @property
    def address(self) -> str:
        """Get the IP address as string."""
        return str(self.interface.ip)

    @property
    def target_network(self) -> ipaddress.IPv4Network:
        """Returns the respective target-side network."""
        target_a_prefix = ipaddress.IPv4Network("100.127.0.0/17")
        target_b_prefix = ipaddress.IPv4Network("100.127.128.0/17")
        client_a_prefix = ipaddress.IPv4Network("100.126.0.0/17")
        client_b_prefix = ipaddress.IPv4Network("100.126.128.0/17")

        if self.interface.ip in client_a_prefix:
            return target_a_prefix
        elif self.interface.ip in client_b_prefix:
            return target_b_prefix
        else:
            raise ValueError(
                f"Cannot determine the target-side network from {self.interface}"
            )

    @property
    def address_with_prefix(self) -> str:
        """Get the IP address with prefix as string."""
        return str(self.interface)

    @property
    def network(self) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
        """Get the network this IP belongs to."""
        return self.interface.network

    @property
    def netmask(self):
        return str(self.interface.netmask)

    @property
    def ip_version(self) -> int:
        """Get the IP version (4 or 6)."""
        return self.interface.version

    def is_ipv4(self) -> bool:
        """Check if this is an IPv4 address."""
        return self.ip_version == 4

    def is_in_subnet(self, subnet: str) -> bool:
        """Check if this IP address is within the specified subnet."""
        try:
            target_subnet = ipaddress.ip_network(subnet)
            return self.network.subnet_of(target_subnet)  # pyright: ignore
        except (ipaddress.AddressValueError, ValueError):
            return False

    @property
    def calculated_gateway(self) -> str:
        """Calculate the first address of the subnet as gateway."""
        first_host = self.network.network_address + 1
        return str(first_host)


@dataclass
class IPAddressAssignment:
    """Represents an IP address assignment to an interface."""

    ip_address: IPAddress


@dataclass
class Interface:
    """Represents a network interface from Nautobot."""

    id: str | None
    mac_address: str | None
    ip_address_assignments: list[IPAddressAssignment]

    def get_ipv4_assignments(self) -> list[IPAddressAssignment]:
        """Get only IPv4 address assignments."""
        return [
            assignment
            for assignment in self.ip_address_assignments
            if assignment.ip_address.is_ipv4()
        ]

    def get_first_ipv4_assignment(self) -> IPAddressAssignment | None:
        """Get the first IPv4 address assignment."""
        ipv4_assignments = self.get_ipv4_assignments()
        return ipv4_assignments[0] if ipv4_assignments else None

    def has_ip_in_subnet(self, subnet: str) -> bool:
        """Check if any IP assignment is in the specified subnet."""
        return any(
            assignment.ip_address.is_in_subnet(subnet)
            for assignment in self.ip_address_assignments
        )

    def is_valid_for_config(self) -> bool:
        """Check if interface is valid for network configuration."""
        return (
            self.mac_address is not None
            and len(self.ip_address_assignments) > 0
            and self.get_first_ipv4_assignment() is not None
        )

    def as_openstack_link(self, if_index=0) -> dict[str, str | int | None]:
        return {
            "id": f"tap-stor-{if_index}",
            "vif_id": self.id,
            "type": "phy",
            "mtu": 9000,
            "ethernet_mac_address": self.mac_address,
        }

    def as_openstack_network(self, if_index=0) -> dict[str, str | int | list | None]:
        ip_assignment = self.get_first_ipv4_assignment()
        if not ip_assignment:
            return {}
        ip = ip_assignment.ip_address
        return {
            "id": f"network-for-if{if_index}",
            "type": "ipv4",
            "link": f"tap-stor-{if_index}",
            "ip_address": ip.address,
            "netmask": str(ip.netmask),
            "routes": [
                {
                    "network": str(ip.target_network.network_address),
                    "netmask": str(ip.target_network.netmask),
                    "gateway": ip.calculated_gateway,
                }
            ],
            "network_id": uuid.uuid4().hex,
        }


@dataclass
class Device:
    """Represents a device from Nautobot."""

    id: str
    interfaces: list[Interface]

    def get_active_interfaces(self) -> list[Interface]:
        """Get interfaces that are valid for network configuration."""
        return [
            interface
            for interface in self.interfaces
            if interface.is_valid_for_config()
        ]

    def get_storage_interfaces(
        self, storage_subnet: str = "100.126.0.0/16"
    ) -> list[Interface]:
        """Get interfaces with IPs in the storage subnet."""
        return [
            interface
            for interface in self.get_active_interfaces()
            if interface.has_ip_in_subnet(storage_subnet)
        ]


@dataclass
class DeviceInterfacesResponse:
    """Represents the complete response from get_device_interfaces."""

    devices: list[Device]

    @classmethod
    def from_graphql_response(cls, response: dict) -> "DeviceInterfacesResponse":
        """Create instance from GraphQL response data."""
        devices_data = response.get("data", {}).get("devices", [])
        devices = []

        for device_data in devices_data:
            interfaces_data = device_data.get("interfaces", [])
            interfaces = []

            for interface_data in interfaces_data:
                assignments_data = interface_data.get("ip_address_assignments", [])
                assignments = []

                for assignment_data in assignments_data:
                    ip_data = assignment_data.get("ip_address", {})
                    address_str = ip_data.get("address", "")
                    if address_str:
                        try:
                            ip_address = IPAddress.from_address_string(address_str)
                            assignments.append(
                                IPAddressAssignment(ip_address=ip_address)
                            )
                        except ValueError:
                            # Skip invalid IP addresses
                            continue

                interface = Interface(
                    id=interface_data.get("id"),
                    mac_address=interface_data.get("mac_address"),
                    ip_address_assignments=assignments,
                )
                interfaces.append(interface)

            device = Device(id=device_data.get("id", ""), interfaces=interfaces)
            devices.append(device)

        return cls(devices=devices)


class NautobotClient:
    """Client for interacting with Nautobot's GraphQL API."""

    def __init__(self, base_url: str, api_key: str):
        """Initialize the Nautobot client.

        Args:
            base_url: Base URL of the Nautobot instance (e.g., 'https://nautobot.example.com')
            api_key: API key for authentication
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.graphql_url = f"{self.base_url}/api/graphql/"

    def _make_graphql_request(self, query: str, variables: dict | None = None) -> dict:
        """Make a GraphQL request to Nautobot.

        Args:
            query: GraphQL query string
            variables: Optional variables for the query

        Returns:
            Response data from the GraphQL endpoint

        Raises:
            requests.RequestException: If the request fails
            ValueError: If the response contains GraphQL errors
        """
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {"query": query, "variables": variables or {}}

        response = requests.post(
            self.graphql_url, headers=headers, json=payload, timeout=30
        )
        response.raise_for_status()

        data = response.json()

        if "errors" in data:
            raise ValueError(f"GraphQL errors: {data['errors']}")

        return data

    def get_device_interfaces(self, device_id: str) -> DeviceInterfacesResponse:
        """Retrieve device interfaces and their IP assignments from Nautobot.

        Args:
            device_id: UUID of the device to query

        Returns:
            DeviceInterfacesResponse containing structured interface data
        """
        query = """
        query ($device_id: String) {
            devices(id: [$device_id]) {
                id
                interfaces(status: "Active") {
                    id
                    mac_address
                    ip_address_assignments {
                        ip_address {
                            address
                            ip_version
                        }
                    }
                }
            }
        }
        """

        variables = {"device_id": device_id}
        response = self._make_graphql_request(query, variables)

        return DeviceInterfacesResponse.from_graphql_response(response)

    def generate_network_config(
        self, response: DeviceInterfacesResponse, ignore_non_storage: bool = False
    ) -> dict[str, list[dict]]:
        """Generate netplan YAML configuration from Nautobot response.

        Args:
            response: Response data from get_device_interfaces method
            ignore_non_storage: If True, only include interfaces with IPs in
                                100.126.0.0/16 subnet

        Returns:
            OpenStack compatible network_data dictionary
        """
        config = {"links": [], "networks": []}

        # To avoid conflict we start indexing from 100
        interface_count = 100

        for device in response.devices:
            # Get appropriate interfaces based on filtering
            if ignore_non_storage:
                interfaces = device.get_storage_interfaces()
            else:
                interfaces = device.get_active_interfaces()

            for interface in interfaces:
                # Get the first IPv4 assignment
                first_assignment = interface.get_first_ipv4_assignment()
                if not first_assignment:
                    continue

                config["links"].append(
                    interface.as_openstack_link(if_index=interface_count)
                )
                config["networks"].append(
                    interface.as_openstack_network(if_index=interface_count)
                )

                interface_count += 1

        return config

    def storage_network_config_for_node(self, node_id: UUID):
        response = self.get_device_interfaces(str(node_id))
        return self.generate_network_config(response, ignore_non_storage=True)
