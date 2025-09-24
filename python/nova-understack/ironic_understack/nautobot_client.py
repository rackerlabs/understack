import ipaddress

import requests
import yaml


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

    def get_device_interfaces(self, device_id: str) -> dict:
        """Retrieve device interfaces and their IP assignments from Nautobot.

        Args:
            device_id: UUID of the device to query

        Returns:
            Dictionary containing the GraphQL response data
        """
        query = """
        query ($device_id: String) {
            devices(id: [$device_id]) {
                id
                interfaces(status: "Active") {
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

        return response

    def _calculate_gateway(self, ip_with_prefix: str) -> str:
        """Calculate the first address of the subnet as gateway.

        Args:
            ip_with_prefix: IP address with prefix (e.g., '192.168.1.10/24')

        Returns:
            First address of the subnet (e.g., '192.168.1.1')
        """
        network = ipaddress.ip_network(ip_with_prefix, strict=False)
        # Get the first host address (network address + 1)
        first_host = network.network_address + 1
        return str(first_host)

    def generate_network_config(
        self, response: dict, ignore_non_storage: bool = False
    ) -> str:
        """Generate netplan YAML configuration from Nautobot response.

        Args:
            response: Response data from get_device_interfaces method
            ignore_non_storage: If True, only include interfaces with IPs in
                                100.126.0.0/16 subnet

        Returns:
            YAML string containing netplan configuration
        """
        config = {"version": 2, "ethernets": {}}

        interface_count = 0

        # Extract devices from response
        devices = response.get("data", {}).get("devices", [])

        for device in devices:
            interfaces = device.get("interfaces", [])

            for interface in interfaces:
                mac_address = interface.get("mac_address")
                ip_assignments = interface.get("ip_address_assignments", [])

                # Only process interfaces with IP assignments
                if not ip_assignments or not mac_address:
                    continue

                # Filter for IPv4 assignments only
                ipv4_assignments = [
                    assignment
                    for assignment in ip_assignments
                    if assignment.get("ip_address", {}).get("ip_version") == 4
                ]

                if not ipv4_assignments:
                    continue

                # Take only the first IPv4 assignment
                first_assignment = ipv4_assignments[0]
                ip_info = first_assignment.get("ip_address", {})
                ip_address = ip_info.get("address")

                if not ip_address:
                    continue

                # Only process interfaces with IP addresses in 100.126.0.0/16 subnet
                try:
                    ip_network = ipaddress.ip_network(ip_address, strict=False)
                    target_subnet = ipaddress.ip_network("100.126.0.0/16")
                    if ignore_non_storage and not ip_network.subnet_of(target_subnet):  # pyright: ignore
                        continue
                except (ipaddress.AddressValueError, ValueError):
                    # Skip if IP address is invalid
                    continue

                interface_name = f"interface{interface_count}"

                # Calculate gateway (first address of the subnet)
                gateway = self._calculate_gateway(ip_address)

                config["ethernets"][interface_name] = {
                    "match": {"macaddress": mac_address},
                    "set-name": interface_name,
                    "addresses": [ip_address],
                    "gateway4": gateway,
                }

                interface_count += 1

        return yaml.dump(config, default_flow_style=False, sort_keys=False)
