"""Unit tests for NautobotClient and related classes."""

import ipaddress
import uuid
from unittest.mock import Mock
from unittest.mock import patch

import pytest
import requests

from ironic_understack.nautobot_client import Device
from ironic_understack.nautobot_client import DeviceInterfacesResponse
from ironic_understack.nautobot_client import Interface
from ironic_understack.nautobot_client import IPAddress
from ironic_understack.nautobot_client import IPAddressAssignment
from ironic_understack.nautobot_client import NautobotClient


class TestIPAddress:
    """Test cases for IPAddress class."""

    def test_from_address_string_ipv4(self):
        """Test creating IPAddress from IPv4 string."""
        ip = IPAddress.from_address_string("192.168.1.10/24")

        assert ip.address == "192.168.1.10"
        assert ip.address_with_prefix == "192.168.1.10/24"
        assert ip.netmask == "255.255.255.0"
        assert ip.ip_version == 4
        assert ip.is_ipv4() is True

    def test_from_address_string_ipv6(self):
        """Test creating IPAddress from IPv6 string."""
        ip = IPAddress.from_address_string("2001:db8::1/64")

        assert ip.address == "2001:db8::1"
        assert ip.address_with_prefix == "2001:db8::1/64"
        assert ip.ip_version == 6
        assert ip.is_ipv4() is False

    def test_from_address_string_invalid(self):
        """Test creating IPAddress from invalid string."""
        with pytest.raises(
            ValueError, match="does not appear to be an IPv4 or IPv6 interface"
        ):
            IPAddress.from_address_string("invalid-ip")

    def test_network_property(self):
        """Test network property."""
        ip = IPAddress.from_address_string("192.168.1.10/24")

        expected_network = ipaddress.IPv4Network("192.168.1.0/24")
        assert ip.network == expected_network

    def test_target_network_octet_0(self):
        """Test target_network calculation for third octet 0."""
        ip = IPAddress.from_address_string("100.126.0.10/24")

        expected_network = ipaddress.IPv4Network("100.127.0.0/17")
        assert ip.target_network == expected_network

    def test_target_network_octet_128(self):
        """Test target_network calculation for third octet 128."""
        ip = IPAddress.from_address_string("100.126.128.10/24")

        expected_network = ipaddress.IPv4Network("100.127.128.0/17")
        assert ip.target_network == expected_network

    def test_target_network_invalid_octet(self):
        """Test target_network with invalid third octet."""
        ip = IPAddress.from_address_string("100.127.64.10/24")

        with pytest.raises(
            ValueError, match="Cannot determine the target-side network"
        ):
            _ = ip.target_network

    def test_is_in_subnet_true(self):
        """Test is_in_subnet returns True for matching subnet."""
        ip = IPAddress.from_address_string("192.168.1.10/24")

        assert ip.is_in_subnet("192.168.0.0/16") is True

    def test_is_in_subnet_false(self):
        """Test is_in_subnet returns False for non-matching subnet."""
        ip = IPAddress.from_address_string("192.168.1.10/24")

        assert ip.is_in_subnet("10.0.0.0/8") is False

    def test_is_in_subnet_invalid_subnet(self):
        """Test is_in_subnet with invalid subnet."""
        ip = IPAddress.from_address_string("192.168.1.10/24")

        assert ip.is_in_subnet("invalid-subnet") is False

    def test_calculated_gateway(self):
        """Test calculated gateway (first host in network)."""
        ip = IPAddress.from_address_string("192.168.1.10/24")

        assert ip.calculated_gateway == "192.168.1.1"


class TestInterface:
    """Test cases for Interface class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.ip_assignment = IPAddressAssignment(
            ip_address=IPAddress.from_address_string("192.168.1.10/24")
        )
        self.ipv6_assignment = IPAddressAssignment(
            ip_address=IPAddress.from_address_string("2001:db8::1/64")
        )

    def test_get_ipv4_assignments(self):
        """Test filtering IPv4 assignments."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ip_assignment, self.ipv6_assignment],
        )

        ipv4_assignments = interface.get_ipv4_assignments()

        assert len(ipv4_assignments) == 1
        assert ipv4_assignments[0] == self.ip_assignment

    def test_get_first_ipv4_assignment(self):
        """Test getting first IPv4 assignment."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ipv6_assignment, self.ip_assignment],
        )

        first_ipv4 = interface.get_first_ipv4_assignment()

        assert first_ipv4 == self.ip_assignment

    def test_get_first_ipv4_assignment_none(self):
        """Test getting first IPv4 assignment when none exist."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ipv6_assignment],
        )

        first_ipv4 = interface.get_first_ipv4_assignment()

        assert first_ipv4 is None

    def test_has_ip_in_subnet_true(self):
        """Test has_ip_in_subnet returns True."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ip_assignment],
        )

        assert interface.has_ip_in_subnet("192.168.0.0/16") is True

    def test_has_ip_in_subnet_false(self):
        """Test has_ip_in_subnet returns False."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ip_assignment],
        )

        assert interface.has_ip_in_subnet("10.0.0.0/8") is False

    def test_is_valid_for_config_true(self):
        """Test interface is valid for configuration."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ip_assignment],
        )

        assert interface.is_valid_for_config() is True

    def test_is_valid_for_config_no_mac(self):
        """Test interface is invalid without MAC address."""
        interface = Interface(
            id="interface-1",
            mac_address=None,
            ip_address_assignments=[self.ip_assignment],
        )

        assert interface.is_valid_for_config() is False

    def test_is_valid_for_config_no_ip(self):
        """Test interface is invalid without IP assignments."""
        interface = Interface(
            id="interface-1", mac_address="aa:bb:cc:dd:ee:ff", ip_address_assignments=[]
        )

        assert interface.is_valid_for_config() is False

    def test_is_valid_for_config_no_ipv4(self):
        """Test interface is invalid without IPv4 assignments."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ipv6_assignment],
        )

        assert interface.is_valid_for_config() is False

    def test_as_openstack_link(self):
        """Test OpenStack link generation."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ip_assignment],
        )

        link = interface.as_openstack_link(if_index=5)

        expected = {
            "id": "tap-stor-5",
            "vif_id": "interface-1",
            "type": "phy",
            "mtu": 9000,
            "ethernet_mac_address": "aa:bb:cc:dd:ee:ff",
        }
        assert link == expected

    def test_as_openstack_network(self):
        """Test OpenStack network generation."""
        # Create IP with specific values for predictable gateway calculation
        ip_assignment = IPAddressAssignment(
            ip_address=IPAddress.from_address_string("100.126.0.10/24")
        )
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[ip_assignment],
        )

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "test-network-id"

            network = interface.as_openstack_network(if_index=5)

        expected = {
            "id": "network-for-if5",
            "type": "ipv4",
            "link": "tap-stor-5",
            "ip_address": "100.126.0.10",
            "netmask": "255.255.255.0",
            "routes": [
                {
                    "network": "100.127.0.0",
                    "netmask": "255.255.128.0",
                    "gateway": "100.126.0.1",
                }
            ],
            "network_id": "test-network-id",
        }
        assert network == expected

    def test_as_openstack_network_no_ipv4(self):
        """Test OpenStack network generation without IPv4."""
        interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[self.ipv6_assignment],
        )

        network = interface.as_openstack_network()

        assert network == {}


class TestDevice:
    """Test cases for Device class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.valid_interface = Interface(
            id="interface-1",
            mac_address="aa:bb:cc:dd:ee:ff",
            ip_address_assignments=[
                IPAddressAssignment(
                    ip_address=IPAddress.from_address_string("192.168.1.10/24")
                )
            ],
        )
        self.invalid_interface = Interface(
            id="interface-2", mac_address=None, ip_address_assignments=[]
        )
        self.storage_interface = Interface(
            id="interface-3",
            mac_address="11:22:33:44:55:66",
            ip_address_assignments=[
                IPAddressAssignment(
                    ip_address=IPAddress.from_address_string("100.126.1.10/24")
                )
            ],
        )

    def test_get_active_interfaces(self):
        """Test filtering active interfaces."""
        device = Device(
            id="device-1",
            interfaces=[
                self.valid_interface,
                self.invalid_interface,
                self.storage_interface,
            ],
        )

        active_interfaces = device.get_active_interfaces()

        assert len(active_interfaces) == 2
        assert self.valid_interface in active_interfaces
        assert self.storage_interface in active_interfaces
        assert self.invalid_interface not in active_interfaces

    def test_get_storage_interfaces_default_subnet(self):
        """Test filtering storage interfaces with default subnet."""
        device = Device(
            id="device-1", interfaces=[self.valid_interface, self.storage_interface]
        )

        storage_interfaces = device.get_storage_interfaces()

        assert len(storage_interfaces) == 1
        assert storage_interfaces[0] == self.storage_interface

    def test_get_storage_interfaces_custom_subnet(self):
        """Test filtering storage interfaces with custom subnet."""
        device = Device(
            id="device-1", interfaces=[self.valid_interface, self.storage_interface]
        )

        storage_interfaces = device.get_storage_interfaces("192.168.0.0/16")

        assert len(storage_interfaces) == 1
        assert storage_interfaces[0] == self.valid_interface


class TestDeviceInterfacesResponse:
    """Test cases for DeviceInterfacesResponse class."""

    def test_from_graphql_response_complete(self):
        """Test parsing complete GraphQL response."""
        graphql_response = {
            "data": {
                "devices": [
                    {
                        "id": "device-1",
                        "interfaces": [
                            {
                                "id": "interface-1",
                                "mac_address": "aa:bb:cc:dd:ee:ff",
                                "ip_address_assignments": [
                                    {"ip_address": {"address": "192.168.1.10/24"}}
                                ],
                            }
                        ],
                    }
                ]
            }
        }

        response = DeviceInterfacesResponse.from_graphql_response(graphql_response)

        assert len(response.devices) == 1
        device = response.devices[0]
        assert device.id == "device-1"
        assert len(device.interfaces) == 1

        interface = device.interfaces[0]
        assert interface.id == "interface-1"
        assert interface.mac_address == "aa:bb:cc:dd:ee:ff"
        assert len(interface.ip_address_assignments) == 1

        assignment = interface.ip_address_assignments[0]
        assert assignment.ip_address.address == "192.168.1.10"

    def test_from_graphql_response_invalid_ip(self):
        """Test parsing GraphQL response with invalid IP address."""
        graphql_response = {
            "data": {
                "devices": [
                    {
                        "id": "device-1",
                        "interfaces": [
                            {
                                "id": "interface-1",
                                "mac_address": "aa:bb:cc:dd:ee:ff",
                                "ip_address_assignments": [
                                    {"ip_address": {"address": "invalid-ip"}},
                                    {"ip_address": {"address": "192.168.1.10/24"}},
                                ],
                            }
                        ],
                    }
                ]
            }
        }

        response = DeviceInterfacesResponse.from_graphql_response(graphql_response)

        # Should skip invalid IP and include valid one
        interface = response.devices[0].interfaces[0]
        assert len(interface.ip_address_assignments) == 1
        assert interface.ip_address_assignments[0].ip_address.address == "192.168.1.10"

    def test_from_graphql_response_empty(self):
        """Test parsing empty GraphQL response."""
        graphql_response = {"data": {"devices": []}}

        response = DeviceInterfacesResponse.from_graphql_response(graphql_response)

        assert len(response.devices) == 0

    def test_from_graphql_response_missing_data(self):
        """Test parsing GraphQL response with missing data."""
        graphql_response = {}

        response = DeviceInterfacesResponse.from_graphql_response(graphql_response)

        assert len(response.devices) == 0


class TestNautobotClient:
    """Test cases for NautobotClient class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.base_url = "https://nautobot.example.com"
        self.api_key = "test-api-key"
        self.client = NautobotClient(self.base_url, self.api_key)

    def test_init(self):
        """Test NautobotClient initialization."""
        assert self.client.base_url == self.base_url
        assert self.client.api_key == self.api_key
        assert self.client.graphql_url == f"{self.base_url}/api/graphql/"

    def test_init_url_stripping(self):
        """Test URL stripping during initialization."""
        client = NautobotClient("https://nautobot.example.com/", self.api_key)

        assert client.base_url == "https://nautobot.example.com"

    @patch("requests.post")
    def test_make_graphql_request_success(self, mock_post):
        """Test successful GraphQL request."""
        expected_response = {"data": {"test": "value"}}
        mock_post.return_value.json.return_value = expected_response
        mock_post.return_value.raise_for_status = Mock()

        query = "query { test }"
        variables = {"var1": "value1"}

        result = self.client._make_graphql_request(query, variables)

        assert result == expected_response

        # Verify request parameters
        mock_post.assert_called_once_with(
            self.client.graphql_url,
            headers={
                "Authorization": f"Token {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": variables},
            timeout=30,
        )

    @patch("requests.post")
    def test_make_graphql_request_no_variables(self, mock_post):
        """Test GraphQL request without variables."""
        expected_response = {"data": {"test": "value"}}
        mock_post.return_value.json.return_value = expected_response
        mock_post.return_value.raise_for_status = Mock()

        query = "query { test }"

        self.client._make_graphql_request(query)

        # Verify empty variables dict was used
        call_args = mock_post.call_args[1]["json"]
        assert call_args["variables"] == {}

    @patch("requests.post")
    def test_make_graphql_request_http_error(self, mock_post):
        """Test GraphQL request with HTTP error."""
        mock_post.return_value.raise_for_status.side_effect = requests.RequestException(
            "HTTP Error"
        )

        with pytest.raises(requests.RequestException):
            self.client._make_graphql_request("query { test }")

    @patch("requests.post")
    def test_make_graphql_request_graphql_errors(self, mock_post):
        """Test GraphQL request with GraphQL errors."""
        error_response = {"errors": [{"message": "GraphQL error"}], "data": None}
        mock_post.return_value.json.return_value = error_response
        mock_post.return_value.raise_for_status = Mock()

        with pytest.raises(ValueError, match="GraphQL errors"):
            self.client._make_graphql_request("query { test }")

    @patch.object(NautobotClient, "_make_graphql_request")
    def test_get_device_interfaces(self, mock_graphql):
        """Test getting device interfaces."""
        mock_response = {
            "data": {
                "devices": [
                    {
                        "id": "device-1",
                        "interfaces": [
                            {
                                "id": "interface-1",
                                "mac_address": "aa:bb:cc:dd:ee:ff",
                                "ip_address_assignments": [
                                    {"ip_address": {"address": "192.168.1.10/24"}}
                                ],
                            }
                        ],
                    }
                ]
            }
        }
        mock_graphql.return_value = mock_response

        device_id = "test-device-id"
        result = self.client.get_device_interfaces(device_id)

        expected_variables = {"device_id": device_id}

        mock_graphql.assert_called_once()
        call_args = mock_graphql.call_args
        assert call_args[0][1] == expected_variables  # variables parameter

        # Verify response parsing
        assert isinstance(result, DeviceInterfacesResponse)
        assert len(result.devices) == 1

    def test_generate_network_config_all_interfaces(self):
        """Test generating network config for all interfaces."""
        # Create mock response with valid target network IPs
        device = Device(
            id="device-1",
            interfaces=[
                Interface(
                    id="interface-1",
                    mac_address="aa:bb:cc:dd:ee:ff",
                    ip_address_assignments=[
                        IPAddressAssignment(
                            ip_address=IPAddress.from_address_string("100.126.0.10/24")
                        )
                    ],
                ),
                Interface(
                    id="interface-2",
                    mac_address="11:22:33:44:55:66",
                    ip_address_assignments=[
                        IPAddressAssignment(
                            ip_address=IPAddress.from_address_string(
                                "100.126.128.10/24"
                            )
                        )
                    ],
                ),
            ],
        )
        response = DeviceInterfacesResponse(devices=[device])

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "test-network-id"

            config = self.client.generate_network_config(
                response, ignore_non_storage=False
            )

        assert len(config["links"]) == 2
        assert len(config["networks"]) == 2

        # Verify interface indexing starts from 100
        assert config["links"][0]["id"] == "tap-stor-100"
        assert config["links"][1]["id"] == "tap-stor-101"

    def test_generate_network_config_storage_only(self):
        """Test generating network config for storage interfaces only."""
        device = Device(
            id="device-1",
            interfaces=[
                Interface(
                    id="interface-1",
                    mac_address="aa:bb:cc:dd:ee:ff",
                    ip_address_assignments=[
                        IPAddressAssignment(
                            ip_address=IPAddress.from_address_string("192.168.1.10/24")
                        )
                    ],
                ),
                Interface(
                    id="interface-2",
                    mac_address="11:22:33:44:55:66",
                    ip_address_assignments=[
                        IPAddressAssignment(
                            ip_address=IPAddress.from_address_string("100.126.0.10/24")
                        )
                    ],
                ),
            ],
        )
        response = DeviceInterfacesResponse(devices=[device])

        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.return_value.hex = "test-network-id"

            config = self.client.generate_network_config(
                response, ignore_non_storage=True
            )

        # Should only include storage interface (100.126.x.x)
        assert len(config["links"]) == 1
        assert len(config["networks"]) == 1

    @patch.object(NautobotClient, "get_device_interfaces")
    @patch.object(NautobotClient, "generate_network_config")
    def test_storage_network_config_for_node(self, mock_generate, mock_get_interfaces):
        """Test getting storage network config for a node."""
        node_id = uuid.uuid4()
        mock_response = Mock()
        mock_get_interfaces.return_value = mock_response
        mock_generate.return_value = {"test": "config"}

        result = self.client.storage_network_config_for_node(node_id)

        mock_get_interfaces.assert_called_once_with(str(node_id))
        mock_generate.assert_called_once_with(mock_response, ignore_non_storage=True)
        assert result == {"test": "config"}
