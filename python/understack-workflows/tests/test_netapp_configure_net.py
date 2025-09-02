import argparse
import json
import pathlib
from contextlib import nullcontext
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from understack_workflows.main.netapp_configure_net import VIRTUAL_MACHINES_QUERY
from understack_workflows.main.netapp_configure_net import InterfaceInfo
from understack_workflows.main.netapp_configure_net import VirtualMachineNetworkInfo
from understack_workflows.main.netapp_configure_net import argument_parser
from understack_workflows.main.netapp_configure_net import construct_device_name
from understack_workflows.main.netapp_configure_net import execute_graphql_query
from understack_workflows.main.netapp_configure_net import netapp_create_interfaces
from understack_workflows.main.netapp_configure_net import (
    validate_and_transform_response,
)


def load_json_sample(filename: str) -> dict:
    """Load JSON sample data from the json_samples directory."""
    here = pathlib.Path(__file__).parent
    sample_path = here / "json_samples" / filename
    with sample_path.open("r") as f:
        return json.load(f)


class TestArgumentParser:
    """Test cases for argument parsing functionality."""

    def test_valid_argument_combinations_with_all_args(self):
        """Test valid argument combinations with all arguments provided."""
        parser = argument_parser()
        args = parser.parse_args(
            [
                "--project-id",
                "12345678-1234-5678-9abc-123456789012",
                "--nautobot_url",
                "http://nautobot.example.com",
                "--nautobot_token",
                "test-token-456",
            ]
        )

        assert args.project_id == "12345678123456789abc123456789012"
        assert args.nautobot_url == "http://nautobot.example.com"
        assert args.nautobot_token == "test-token-456"

    def test_valid_argument_combinations_with_required_only(self):
        """Test valid argument combinations with only required arguments."""
        parser = argument_parser()
        args = parser.parse_args(
            ["--project-id", "abcdef12-3456-7890-abcd-ef1234567890"]
        )

        assert args.project_id == "abcdef1234567890abcdef1234567890"
        # Should use default nautobot_url
        assert args.nautobot_url == "http://nautobot-default.nautobot.svc.cluster.local"
        # nautobot_token should be None when not provided
        assert args.nautobot_token is None

    def test_valid_argument_combinations_with_https_url(self):
        """Test valid argument combinations with HTTPS URL."""
        parser = argument_parser()
        args = parser.parse_args(
            [
                "--project-id",
                "fedcba98-7654-3210-fedc-ba9876543210",
                "--nautobot_url",
                "https://secure.nautobot.example.com:8443",
                "--nautobot_token",
                "secure-token",
            ]
        )

        assert args.project_id == "fedcba9876543210fedcba9876543210"
        assert args.nautobot_url == "https://secure.nautobot.example.com:8443"
        assert args.nautobot_token == "secure-token"

    def test_required_arguments_project_id_validation(self):
        """Test that project_id is required and validated."""
        parser = argument_parser()

        # Test missing project_id raises SystemExit
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "--nautobot_url",
                    "http://nautobot.example.com",
                    "--nautobot_token",
                    "test-token",
                ]
            )

    def test_required_arguments_empty_project_id(self):
        """Test that empty project_id is rejected (UUID validation)."""
        parser = argument_parser()

        # Empty string should be rejected as it's not a valid UUID
        with pytest.raises(SystemExit):
            parser.parse_args(["--project-id", ""])

    @pytest.mark.parametrize(
        "url,context,expected_url",
        [
            # Valid URLs
            ("http://localhost", nullcontext(), "http://localhost"),
            (
                "https://nautobot.example.com",
                nullcontext(),
                "https://nautobot.example.com",
            ),
            (
                "http://nautobot.example.com:8080",
                nullcontext(),
                "http://nautobot.example.com:8080",
            ),
            (
                "https://nautobot.example.com:8443/api",
                nullcontext(),
                "https://nautobot.example.com:8443/api",
            ),
            # Invalid URLs should raise SystemExit
            ("", pytest.raises(SystemExit), None),
            ("http", pytest.raises(SystemExit), None),
            ("localhost", pytest.raises(SystemExit), None),
            ("://invalid", pytest.raises(SystemExit), None),
            ("http://", pytest.raises(SystemExit), None),
            (
                "ftp://invalid.scheme.com",
                nullcontext(),
                "ftp://invalid.scheme.com",
            ),  # ftp is valid URL scheme
        ],
    )
    def test_url_format_validation(self, url, context, expected_url):
        """Test URL format validation for nautobot_url argument."""
        parser = argument_parser()

        with context:
            args = parser.parse_args(
                [
                    "--project-id",
                    "11111111-2222-3333-4444-555555555555",
                    "--nautobot_url",
                    url,
                ]
            )
            assert args.nautobot_url == expected_url

    def test_default_value_handling_nautobot_url(self):
        """Test default value handling for nautobot_url."""
        parser = argument_parser()
        args = parser.parse_args(
            ["--project-id", "22222222-3333-4444-5555-666666666666"]
        )

        # Should use the default URL
        assert args.nautobot_url == "http://nautobot-default.nautobot.svc.cluster.local"

    def test_default_value_handling_nautobot_token(self):
        """Test default value handling for nautobot_token."""
        parser = argument_parser()
        args = parser.parse_args(
            ["--project-id", "33333333-4444-5555-6666-777777777777"]
        )

        # nautobot_token should be None when not provided
        assert args.nautobot_token is None

    @pytest.mark.parametrize(
        "token_value,expected_token",
        [
            ("", ""),  # Empty token should be accepted
            ("simple-token", "simple-token"),
            (
                "complex-token-with-123-and-symbols!@#",
                "complex-token-with-123-and-symbols!@#",
            ),
            ("very-long-token-" + "x" * 100, "very-long-token-" + "x" * 100),
        ],
    )
    def test_default_value_handling_token_variations(self, token_value, expected_token):
        """Test various token values are handled correctly."""
        parser = argument_parser()
        args = parser.parse_args(
            [
                "--project-id",
                "44444444-5555-6666-7777-888888888888",
                "--nautobot_token",
                token_value,
            ]
        )

        assert args.nautobot_token == expected_token

    def test_error_cases_missing_required_project_id(self):
        """Test error case when required project_id argument is missing."""
        parser = argument_parser()

        # Should raise SystemExit when project_id is missing
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_error_cases_missing_required_project_id_with_other_args(self):
        """Test error case when project_id is missing but other args provided."""
        parser = argument_parser()

        # Should raise SystemExit when project_id is missing, even with other
        # valid args
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "--nautobot_url",
                    "http://nautobot.example.com",
                    "--nautobot_token",
                    "test-token",
                ]
            )

    def test_error_cases_invalid_argument_names(self):
        """Test error cases with invalid argument names."""
        parser = argument_parser()

        # Test invalid argument name
        with pytest.raises(SystemExit):
            parser.parse_args(
                ["--project-id", "test-project", "--invalid-argument", "value"]
            )

    def test_error_cases_malformed_arguments(self):
        """Test error cases with malformed arguments."""
        parser = argument_parser()

        # Test argument without value
        with pytest.raises(SystemExit):
            parser.parse_args(["--project-id"])

    @pytest.mark.parametrize(
        "project_id_value",
        [
            "simple-project",
            "project-with-dashes",
            "project_with_underscores",
            "project123",
            "PROJECT-UPPERCASE",
            "mixed-Case_Project123",
            "project.with.dots",
            "project/with/slashes",
            "project with spaces",
            "project-with-special-chars!@#$%^&*()",
        ],
    )
    def test_project_id_string_type_validation(self, project_id_value):
        """Test that project_id accepts various string formats."""
        # Note: This test is now obsolete since project_id must be a valid UUID
        # These will fail with UUID validation
        parser = argument_parser()

        # Most of these should now fail with UUID validation
        if project_id_value in [
            "simple-project",
            "project-with-dashes",
            "project_with_underscores",
            "project123",
            "PROJECT-UPPERCASE",
            "mixed-Case_Project123",
            "project.with.dots",
            "project/with/slashes",
            "project with spaces",
            "project-with-special-chars!@#$%^&*()",
        ]:
            with pytest.raises(SystemExit):
                parser.parse_args(["--project-id", project_id_value])
        else:
            args = parser.parse_args(["--project-id", project_id_value])
            assert args.project_id == project_id_value

    def test_argument_parser_help_functionality(self):
        """Test that argument parser provides help functionality."""
        parser = argument_parser()

        # Test that help option raises SystemExit (normal behavior for --help)
        with pytest.raises(SystemExit):
            parser.parse_args(["--help"])

    def test_argument_parser_description(self):
        """Test that argument parser has proper description."""
        parser = argument_parser()

        expected_description = (
            "Query Nautobot for SVM network configuration and create NetApp "
            "interfaces based on project ID"
        )
        assert parser.description == expected_description

    def test_argument_parser_returns_namespace(self):
        """Test that argument parser returns proper Namespace object."""
        parser = argument_parser()
        args = parser.parse_args(
            ["--project-id", "12345678-1234-5678-9abc-123456789012"]
        )

        # Should return argparse.Namespace object
        assert isinstance(args, argparse.Namespace)

        # Should have all expected attributes
        assert hasattr(args, "project_id")
        assert hasattr(args, "nautobot_url")
        assert hasattr(args, "nautobot_token")

    def test_argument_parser_integration_with_parser_nautobot_args(self):
        """Test argument_parser integrates with parser_nautobot_args helper."""
        parser = argument_parser()

        # Verify that nautobot arguments are properly added by the helper
        args = parser.parse_args(
            [
                "--project-id",
                "12345678-1234-5678-9abc-123456789012",
                "--nautobot_url",
                "http://custom.nautobot.com",
                "--nautobot_token",
                "custom-token",
            ]
        )

        # All nautobot args should be present and functional
        assert args.nautobot_url == "http://custom.nautobot.com"
        assert args.nautobot_token == "custom-token"

        # And our custom project_id should also work (UUID without dashes)
        assert args.project_id == "12345678123456789abc123456789012"

    @pytest.mark.parametrize(
        "uuid_input,expected_output",
        [
            # Valid UUIDs with dashes
            (
                "12345678-1234-5678-9abc-123456789012",
                "12345678123456789abc123456789012",
            ),
            (
                "abcdef12-3456-7890-abcd-ef1234567890",
                "abcdef1234567890abcdef1234567890",
            ),
            (
                "00000000-0000-0000-0000-000000000000",
                "00000000000000000000000000000000",
            ),
            (
                "ffffffff-ffff-ffff-ffff-ffffffffffff",
                "ffffffffffffffffffffffffffffffff",
            ),
            # Valid UUIDs without dashes (should still work)
            (
                "12345678123456789abc123456789012",
                "12345678123456789abc123456789012",
            ),
            (
                "abcdef1234567890abcdef1234567890",
                "abcdef1234567890abcdef1234567890",
            ),
            # Mixed case should be normalized to lowercase
            (
                "ABCDEF12-3456-7890-ABCD-EF1234567890",
                "abcdef1234567890abcdef1234567890",
            ),
            (
                "AbCdEf12-3456-7890-AbCd-Ef1234567890",
                "abcdef1234567890abcdef1234567890",
            ),
        ],
    )
    def test_project_id_uuid_validation_valid_cases(self, uuid_input, expected_output):
        """Test that project_id accepts valid UUID formats and normalizes them."""
        parser = argument_parser()
        args = parser.parse_args(["--project-id", uuid_input])

        assert args.project_id == expected_output

    @pytest.mark.parametrize(
        "invalid_uuid",
        [
            # Invalid UUID formats
            "not-a-uuid",
            "12345678-1234-5678-9abc-12345678901",  # Too short
            "12345678-1234-5678-9abc-1234567890123",  # Too long
            "12345678-1234-5678-9abc-123456789g12",  # Invalid character 'g'
            "12345678-1234-5678-9abc",  # Missing parts
            "12345678-1234-5678-9abc-123456789012-extra",  # Extra parts
            "",  # Empty string
            "123",  # Too short
            # Non-hex characters
            "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz",
            "12345678-1234-5678-9abc-12345678901z",
        ],
    )
    def test_project_id_uuid_validation_invalid_cases(self, invalid_uuid):
        """Test that project_id rejects invalid UUID formats."""
        parser = argument_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["--project-id", invalid_uuid])

    def test_project_id_uuid_validation_error_message(self):
        """Test that UUID validation provides helpful error messages."""
        from understack_workflows.main.netapp_configure_net import (
            validate_and_normalize_uuid,
        )

        with pytest.raises(
            argparse.ArgumentTypeError, match="Invalid UUID format: not-a-uuid"
        ):
            validate_and_normalize_uuid("not-a-uuid")

    def test_validate_and_normalize_uuid_function_directly(self):
        """Test the validate_and_normalize_uuid function directly."""
        from understack_workflows.main.netapp_configure_net import (
            validate_and_normalize_uuid,
        )

        # Test valid cases
        assert (
            validate_and_normalize_uuid("12345678-1234-5678-9abc-123456789012")
            == "12345678123456789abc123456789012"
        )
        assert (
            validate_and_normalize_uuid("12345678123456789abc123456789012")
            == "12345678123456789abc123456789012"
        )
        assert (
            validate_and_normalize_uuid("ABCDEF12-3456-7890-ABCD-EF1234567890")
            == "abcdef1234567890abcdef1234567890"
        )

        # Test invalid cases
        with pytest.raises(argparse.ArgumentTypeError):
            validate_and_normalize_uuid("invalid-uuid")

        with pytest.raises(argparse.ArgumentTypeError):
            validate_and_normalize_uuid("")

        with pytest.raises(argparse.ArgumentTypeError):
            validate_and_normalize_uuid(
                "12345678-1234-5678-9abc-12345678901"
            )  # Too short


class TestInterfaceInfo:
    """Test cases for InterfaceInfo data class and validation."""

    def test_interface_info_creation_with_valid_data(self):
        """Test InterfaceInfo creation with valid data."""
        # Test basic creation
        interface = InterfaceInfo(name="eth0", address="192.168.1.10/24", vlan=100)

        assert interface.name == "eth0"
        assert interface.address == "192.168.1.10/24"
        assert interface.vlan == 100

    def test_interface_info_creation_with_various_valid_formats(self):
        """Test InterfaceInfo creation with various valid data formats."""
        test_cases = [
            ("N1-lif-A", "100.127.0.21/29", 2002),
            ("mgmt", "10.0.0.1/8", 1),
            ("bond0.100", "172.16.1.50/16", 4094),
            ("interface-with-long-name", "203.0.113.1/32", 1),
        ]

        for name, address, vlan in test_cases:
            interface = InterfaceInfo(name=name, address=address, vlan=vlan)
            assert interface.name == name
            assert interface.address == address
            assert interface.vlan == vlan

    def test_from_graphql_interface_with_valid_single_ip_and_vlan(self):
        """Test validation of single IP address per interface."""
        # Valid GraphQL interface data with single IP and VLAN
        interface_data = {
            "name": "N1-lif-A",
            "ip_addresses": [{"address": "100.127.0.21/29"}],
            "tagged_vlans": [{"vid": 2002}],
        }

        interface = InterfaceInfo.from_graphql_interface(interface_data)

        assert interface.name == "N1-lif-A"
        assert interface.address == "100.127.0.21/29"
        assert interface.vlan == 2002

    def test_from_graphql_interface_with_various_valid_data(self):
        """Test from_graphql_interface with various valid data formats."""
        test_cases = [
            {
                "name": "eth0",
                "ip_addresses": [{"address": "192.168.1.10/24"}],
                "tagged_vlans": [{"vid": 100}],
            },
            {
                "name": "bond0",
                "ip_addresses": [{"address": "10.0.0.1/8"}],
                "tagged_vlans": [{"vid": 1}],
            },
            {
                "name": "interface-name-with-special-chars_123",
                "ip_addresses": [{"address": "203.0.113.255/32"}],
                "tagged_vlans": [{"vid": 4094}],
            },
        ]

        for interface_data in test_cases:
            interface = InterfaceInfo.from_graphql_interface(interface_data)
            assert interface.name == interface_data["name"]
            assert interface.address == interface_data["ip_addresses"][0]["address"]
            assert interface.vlan == interface_data["tagged_vlans"][0]["vid"]

    def test_validation_single_vlan_id_per_interface(self):
        """Test validation of single VLAN ID per interface."""
        # Valid case with single VLAN
        interface_data = {
            "name": "test-interface",
            "ip_addresses": [{"address": "192.168.1.10/24"}],
            "tagged_vlans": [{"vid": 200}],
        }

        interface = InterfaceInfo.from_graphql_interface(interface_data)
        assert interface.vlan == 200

    def test_error_handling_zero_ip_addresses(self):
        """Test error handling for interfaces with zero IP addresses."""
        interface_data = {
            "name": "no-ip-interface",
            "ip_addresses": [],
            "tagged_vlans": [{"vid": 100}],
        }

        with pytest.raises(
            ValueError, match="Interface 'no-ip-interface' has no IP addresses"
        ):
            InterfaceInfo.from_graphql_interface(interface_data)

    def test_error_handling_multiple_ip_addresses(self):
        """Test error handling for interfaces with multiple IP addresses."""
        interface_data = {
            "name": "multi-ip-interface",
            "ip_addresses": [
                {"address": "192.168.1.10/24"},
                {"address": "192.168.1.11/24"},
            ],
            "tagged_vlans": [{"vid": 100}],
        }

        with pytest.raises(
            ValueError, match="Interface 'multi-ip-interface' has multiple IP addresses"
        ):
            InterfaceInfo.from_graphql_interface(interface_data)

    def test_error_handling_zero_vlans(self):
        """Test error handling for interfaces with zero VLANs."""
        interface_data = {
            "name": "no-vlan-interface",
            "ip_addresses": [{"address": "192.168.1.10/24"}],
            "tagged_vlans": [],
        }

        with pytest.raises(
            ValueError, match="Interface 'no-vlan-interface' has no tagged VLANs"
        ):
            InterfaceInfo.from_graphql_interface(interface_data)

    def test_error_handling_multiple_vlans(self):
        """Test error handling for interfaces with multiple VLANs."""
        interface_data = {
            "name": "multi-vlan-interface",
            "ip_addresses": [{"address": "192.168.1.10/24"}],
            "tagged_vlans": [{"vid": 100}, {"vid": 200}],
        }

        with pytest.raises(
            ValueError,
            match="Interface 'multi-vlan-interface' has multiple tagged VLANs",
        ):
            InterfaceInfo.from_graphql_interface(interface_data)

    def test_error_handling_missing_ip_addresses_key(self):
        """Test error handling when ip_addresses key is missing."""
        interface_data = {"name": "missing-ip-key", "tagged_vlans": [{"vid": 100}]}

        with pytest.raises(
            ValueError, match="Interface 'missing-ip-key' has no IP addresses"
        ):
            InterfaceInfo.from_graphql_interface(interface_data)

    def test_error_handling_missing_tagged_vlans_key(self):
        """Test error handling when tagged_vlans key is missing."""
        interface_data = {
            "name": "missing-vlan-key",
            "ip_addresses": [{"address": "192.168.1.10/24"}],
        }

        with pytest.raises(
            ValueError, match="Interface 'missing-vlan-key' has no tagged VLANs"
        ):
            InterfaceInfo.from_graphql_interface(interface_data)

    def test_error_handling_missing_name_key(self):
        """Test error handling when name key is missing."""
        interface_data = {
            "ip_addresses": [{"address": "192.168.1.10/24"}],
            "tagged_vlans": [{"vid": 100}],
        }

        # Should use empty string for missing name
        interface = InterfaceInfo.from_graphql_interface(interface_data)
        assert interface.name == ""
        assert interface.address == "192.168.1.10/24"
        assert interface.vlan == 100

    def test_error_messages_contain_interface_details(self):
        """Test that error messages contain specific interface details."""
        # Test multiple IP addresses error message contains IP list
        interface_data = {
            "name": "test-interface",
            "ip_addresses": [
                {"address": "192.168.1.10/24"},
                {"address": "10.0.0.1/8"},
                {"address": "172.16.1.1/16"},
            ],
            "tagged_vlans": [{"vid": 100}],
        }

        with pytest.raises(ValueError) as exc_info:
            InterfaceInfo.from_graphql_interface(interface_data)

        error_message = str(exc_info.value)
        assert "192.168.1.10/24" in error_message
        assert "10.0.0.1/8" in error_message
        assert "172.16.1.1/16" in error_message

        # Test multiple VLANs error message contains VLAN list
        interface_data = {
            "name": "test-interface",
            "ip_addresses": [{"address": "192.168.1.10/24"}],
            "tagged_vlans": [{"vid": 100}, {"vid": 200}, {"vid": 300}],
        }

        with pytest.raises(ValueError) as exc_info:
            InterfaceInfo.from_graphql_interface(interface_data)

        error_message = str(exc_info.value)
        assert "100" in error_message
        assert "200" in error_message
        assert "300" in error_message


class TestVirtualMachineNetworkInfo:
    """Test cases for VirtualMachineNetworkInfo data class and validation."""

    def test_virtual_machine_network_info_creation_with_valid_data(self):
        """Test VirtualMachineNetworkInfo creation with valid data."""
        interfaces = [
            InterfaceInfo(name="eth0", address="192.168.1.10/24", vlan=100),
            InterfaceInfo(name="eth1", address="10.0.0.1/8", vlan=200),
        ]

        vm_info = VirtualMachineNetworkInfo(interfaces=interfaces)

        assert len(vm_info.interfaces) == 2
        assert vm_info.interfaces[0].name == "eth0"
        assert vm_info.interfaces[1].name == "eth1"

    def test_virtual_machine_network_info_creation_with_empty_interfaces(self):
        """Test VirtualMachineNetworkInfo creation with empty interfaces list."""
        vm_info = VirtualMachineNetworkInfo(interfaces=[])

        assert len(vm_info.interfaces) == 0
        assert vm_info.interfaces == []

    def test_from_graphql_vm_with_valid_interfaces(self):
        """Test GraphQL response transformation to data classes."""
        vm_data = {
            "interfaces": [
                {
                    "name": "N1-lif-A",
                    "ip_addresses": [{"address": "100.127.0.21/29"}],
                    "tagged_vlans": [{"vid": 2002}],
                },
                {
                    "name": "N1-lif-B",
                    "ip_addresses": [{"address": "100.127.128.21/29"}],
                    "tagged_vlans": [{"vid": 2002}],
                },
            ]
        }

        vm_info = VirtualMachineNetworkInfo.from_graphql_vm(vm_data)

        assert len(vm_info.interfaces) == 2

        # Check first interface
        assert vm_info.interfaces[0].name == "N1-lif-A"
        assert vm_info.interfaces[0].address == "100.127.0.21/29"
        assert vm_info.interfaces[0].vlan == 2002

        # Check second interface
        assert vm_info.interfaces[1].name == "N1-lif-B"
        assert vm_info.interfaces[1].address == "100.127.128.21/29"
        assert vm_info.interfaces[1].vlan == 2002

    def test_from_graphql_vm_with_empty_interfaces(self):
        """Test GraphQL response transformation with empty interfaces."""
        vm_data = {"interfaces": []}

        vm_info = VirtualMachineNetworkInfo.from_graphql_vm(vm_data)

        assert len(vm_info.interfaces) == 0

    def test_from_graphql_vm_with_missing_interfaces_key(self):
        """Test GraphQL response transformation with missing interfaces key."""
        vm_data = {}

        vm_info = VirtualMachineNetworkInfo.from_graphql_vm(vm_data)

        assert len(vm_info.interfaces) == 0

    def test_from_graphql_vm_with_single_interface(self):
        """Test GraphQL response transformation with single interface."""
        vm_data = {
            "interfaces": [
                {
                    "name": "single-interface",
                    "ip_addresses": [{"address": "203.0.113.1/32"}],
                    "tagged_vlans": [{"vid": 4094}],
                }
            ]
        }

        vm_info = VirtualMachineNetworkInfo.from_graphql_vm(vm_data)

        assert len(vm_info.interfaces) == 1
        assert vm_info.interfaces[0].name == "single-interface"
        assert vm_info.interfaces[0].address == "203.0.113.1/32"
        assert vm_info.interfaces[0].vlan == 4094

    def test_from_graphql_vm_propagates_interface_validation_errors(self):
        """Test interface validation errors propagated from VirtualMachineNetworkInfo.

        VirtualMachineNetworkInfo validates interface data and should propagate
        any validation errors that occur during processing.
        """
        # VM data with invalid interface (multiple IP addresses)
        vm_data = {
            "interfaces": [
                {
                    "name": "valid-interface",
                    "ip_addresses": [{"address": "192.168.1.10/24"}],
                    "tagged_vlans": [{"vid": 100}],
                },
                {
                    "name": "invalid-interface",
                    "ip_addresses": [
                        {"address": "192.168.1.11/24"},
                        {"address": "192.168.1.12/24"},
                    ],
                    "tagged_vlans": [{"vid": 200}],
                },
            ]
        }

        with pytest.raises(
            ValueError, match="Interface 'invalid-interface' has multiple IP addresses"
        ):
            VirtualMachineNetworkInfo.from_graphql_vm(vm_data)

    def test_from_graphql_vm_with_complex_realistic_data(self):
        """Test GraphQL response transformation with complex realistic data."""
        # Load complex data from JSON sample and extract the VM data
        sample_data = load_json_sample("nautobot_graphql_vm_response_complex.json")
        vm_data = sample_data["data"]["virtual_machines"][0]

        vm_info = VirtualMachineNetworkInfo.from_graphql_vm(vm_data)

        assert len(vm_info.interfaces) == 4

        # Verify all interfaces are correctly parsed
        expected_interfaces = [
            ("N1-lif-A", "100.127.0.21/29", 2002),
            ("N1-lif-B", "100.127.128.21/29", 2002),
            ("N2-lif-A", "100.127.0.22/29", 2002),
            ("N2-lif-B", "100.127.128.22/29", 2002),
        ]

        for i, (expected_name, expected_address, expected_vlan) in enumerate(
            expected_interfaces
        ):
            assert vm_info.interfaces[i].name == expected_name
            assert vm_info.interfaces[i].address == expected_address
            assert vm_info.interfaces[i].vlan == expected_vlan

    def test_from_graphql_vm_error_handling_preserves_interface_context(self):
        """Test that error handling preserves interface context information."""
        # Test with interface that has no VLANs
        vm_data = {
            "interfaces": [
                {
                    "name": "problematic-interface",
                    "ip_addresses": [{"address": "192.168.1.10/24"}],
                    "tagged_vlans": [],
                }
            ]
        }

        with pytest.raises(ValueError) as exc_info:
            VirtualMachineNetworkInfo.from_graphql_vm(vm_data)

        error_message = str(exc_info.value)
        assert "problematic-interface" in error_message
        assert "no tagged VLANs" in error_message


class TestGraphQLQueryFunctionality:
    """Test cases for GraphQL query construction, execution, and response handling."""

    def test_graphql_query_construction_and_format(self):
        """Test GraphQL query construction and variable substitution."""
        # Test that the query constant is properly formatted
        expected_query = (
            "query ($device_names: [String]){virtual_machines(name: $device_names) "
            "{interfaces { name ip_addresses{ address } tagged_vlans { vid }}}}"
        )
        assert VIRTUAL_MACHINES_QUERY == expected_query

        # Test that the query contains all required fields
        assert "virtual_machines" in VIRTUAL_MACHINES_QUERY
        assert "device_names" in VIRTUAL_MACHINES_QUERY
        assert "interfaces" in VIRTUAL_MACHINES_QUERY
        assert "name" in VIRTUAL_MACHINES_QUERY
        assert "ip_addresses" in VIRTUAL_MACHINES_QUERY
        assert "address" in VIRTUAL_MACHINES_QUERY
        assert "tagged_vlans" in VIRTUAL_MACHINES_QUERY
        assert "vid" in VIRTUAL_MACHINES_QUERY

    def test_graphql_query_variable_substitution_format(self):
        """Test GraphQL query variable substitution format."""
        # Test that variables are properly formatted for GraphQL
        project_id = "test-project-123"
        device_name = construct_device_name(project_id)
        variables = {"device_names": [device_name]}

        # Variables should be a dict with device_names as list
        assert isinstance(variables, dict)
        assert "device_names" in variables
        assert isinstance(variables["device_names"], list)
        assert len(variables["device_names"]) == 1
        assert variables["device_names"][0] == "os-test-project-123"

    def test_device_name_formatting_from_project_id(self):
        """Test device name formatting from project_id.

        The function now expects normalized UUID format for project IDs
        and formats device names accordingly.
        """
        test_cases = [
            ("123456781234567890ab123456789012", "os-123456781234567890ab123456789012"),
            (
                "abcdef12345678900abcdef1234567890",
                "os-abcdef12345678900abcdef1234567890",
            ),
            ("00000000000000000000000000000000", "os-00000000000000000000000000000000"),
            ("ffffffffffffffffffffffffffffffff", "os-ffffffffffffffffffffffffffffffff"),
            (
                "fedcba98765432100fedcba9876543210",
                "os-fedcba98765432100fedcba9876543210",
            ),
        ]

        for project_id, expected_device_name in test_cases:
            device_name = construct_device_name(project_id)
            assert device_name == expected_device_name

    def test_device_name_formatting_consistency(self):
        """Test device name formatting consistency."""
        project_id = "123456781234567890ab123456789012"

        # Multiple calls should return the same result
        device_name1 = construct_device_name(project_id)
        device_name2 = construct_device_name(project_id)

        assert device_name1 == device_name2
        assert device_name1 == "os-123456781234567890ab123456789012"

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_execute_graphql_query_successful_execution(self, mock_logger):
        """Test successful GraphQL query execution with mock Nautobot responses."""
        # Mock successful GraphQL response
        mock_response = Mock()
        mock_response.json = load_json_sample(
            "nautobot_graphql_vm_response_single.json"
        )

        # Mock Nautobot client
        mock_nautobot_client = Mock()
        mock_nautobot_client.session.graphql.query.return_value = mock_response

        # Execute query
        project_id = "123456781234567890ab123456789012"
        result = execute_graphql_query(mock_nautobot_client, project_id)

        # Verify query was called with correct parameters
        expected_variables = {"device_names": ["os-123456781234567890ab123456789012"]}
        mock_nautobot_client.session.graphql.query.assert_called_once_with(
            query=VIRTUAL_MACHINES_QUERY, variables=expected_variables
        )

        # Verify result
        assert result == mock_response.json
        assert "data" in result
        assert "virtual_machines" in result["data"]

        # Verify logging
        mock_logger.debug.assert_called()
        mock_logger.info.assert_called()

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_execute_graphql_query_with_various_project_ids(self, mock_logger):
        """Test GraphQL query execution with various project IDs."""
        test_cases = [
            "123456781234567890ab123456789012",
            "abcdef12345678900abcdef1234567890",
            "00000000000000000000000000000000",
            "ffffffffffffffffffffffffffffffff",
            "fedcba98765432100fedcba9876543210",
        ]

        for project_id in test_cases:
            # Mock successful response
            mock_response = Mock()
            mock_response.json = {"data": {"virtual_machines": []}}

            # Mock Nautobot client
            mock_nautobot_client = Mock()
            mock_nautobot_client.session.graphql.query.return_value = mock_response

            # Execute query
            result = execute_graphql_query(mock_nautobot_client, project_id)

            # Verify correct device name was used
            expected_device_name = f"os-{project_id}"
            expected_variables = {"device_names": [expected_device_name]}

            mock_nautobot_client.session.graphql.query.assert_called_with(
                query=VIRTUAL_MACHINES_QUERY, variables=expected_variables
            )

            assert result == mock_response.json

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_mock_nautobot_api_responses_for_consistent_testing(self, mock_logger):
        """Test mock Nautobot API responses for consistent testing."""
        # Test case 1: Empty response
        mock_response_empty = Mock()
        mock_response_empty.json = {"data": {"virtual_machines": []}}

        mock_nautobot_client = Mock()
        mock_nautobot_client.session.graphql.query.return_value = mock_response_empty

        result = execute_graphql_query(mock_nautobot_client, "empty-project")
        assert result["data"]["virtual_machines"] == []

        # Test case 2: Single VM with multiple interfaces
        mock_response_multi = Mock()
        mock_response_multi.json = {
            "data": {
                "virtual_machines": [
                    {
                        "interfaces": [
                            {
                                "name": "N1-lif-A",
                                "ip_addresses": [{"address": "100.127.0.21/29"}],
                                "tagged_vlans": [{"vid": 2002}],
                            },
                            {
                                "name": "N1-lif-B",
                                "ip_addresses": [{"address": "100.127.128.21/29"}],
                                "tagged_vlans": [{"vid": 2002}],
                            },
                        ]
                    }
                ]
            }
        }

        mock_nautobot_client.session.graphql.query.return_value = mock_response_multi
        result = execute_graphql_query(mock_nautobot_client, "multi-interface-project")

        assert len(result["data"]["virtual_machines"]) == 1
        assert len(result["data"]["virtual_machines"][0]["interfaces"]) == 2

        # Test case 3: Complex realistic response
        mock_response_complex = Mock()
        mock_response_complex.json = {
            "data": {
                "virtual_machines": [
                    {
                        "interfaces": [
                            {
                                "name": "N1-lif-A",
                                "ip_addresses": [{"address": "100.127.0.21/29"}],
                                "tagged_vlans": [{"vid": 2002}],
                            },
                            {
                                "name": "N1-lif-B",
                                "ip_addresses": [{"address": "100.127.128.21/29"}],
                                "tagged_vlans": [{"vid": 2002}],
                            },
                            {
                                "name": "N2-lif-A",
                                "ip_addresses": [{"address": "100.127.0.22/29"}],
                                "tagged_vlans": [{"vid": 2002}],
                            },
                            {
                                "name": "N2-lif-B",
                                "ip_addresses": [{"address": "100.127.128.22/29"}],
                                "tagged_vlans": [{"vid": 2002}],
                            },
                        ]
                    }
                ]
            }
        }

        mock_nautobot_client.session.graphql.query.return_value = mock_response_complex
        result = execute_graphql_query(mock_nautobot_client, "complex-project")

        assert len(result["data"]["virtual_machines"]) == 1
        assert len(result["data"]["virtual_machines"][0]["interfaces"]) == 4

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_error_handling_for_graphql_failures(self, mock_logger):
        """Test error handling for GraphQL failures."""
        # Test case 1: GraphQL execution exception
        mock_nautobot_client = Mock()
        original_exception = Exception("Connection timeout")
        mock_nautobot_client.session.graphql.query.side_effect = original_exception

        with pytest.raises(
            Exception, match="GraphQL query execution failed: Connection timeout"
        ):
            execute_graphql_query(mock_nautobot_client, "test-project")

        mock_logger.error.assert_called_with(
            "Failed to execute GraphQL query: %s", original_exception
        )

        # Test case 2: GraphQL returns no data
        mock_response_no_data = Mock()
        mock_response_no_data.json = None

        mock_nautobot_client.session.graphql.query.side_effect = None
        mock_nautobot_client.session.graphql.query.return_value = mock_response_no_data

        with pytest.raises(Exception, match="GraphQL query returned no data"):
            execute_graphql_query(mock_nautobot_client, "test-project")

        # Test case 3: GraphQL returns errors
        mock_response_with_errors = Mock()
        mock_response_with_errors.json = {
            "errors": [
                {"message": "Field 'virtual_machines' doesn't exist on type 'Query'"},
                {"message": "Syntax error in query"},
            ],
            "data": None,
        }

        mock_nautobot_client.session.graphql.query.return_value = (
            mock_response_with_errors
        )

        with pytest.raises(Exception, match="GraphQL query failed with errors"):
            execute_graphql_query(mock_nautobot_client, "test-project")

        # Verify error logging
        mock_logger.error.assert_called()

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_error_handling_various_graphql_error_formats(self, mock_logger):
        """Test error handling for various GraphQL error formats."""
        mock_nautobot_client = Mock()

        # Test case 1: Single error with message
        mock_response = Mock()
        mock_response.json = {
            "errors": [{"message": "Authentication failed"}],
            "data": None,
        }
        mock_nautobot_client.session.graphql.query.return_value = mock_response

        with pytest.raises(
            Exception, match="GraphQL query failed with errors: Authentication failed"
        ):
            execute_graphql_query(mock_nautobot_client, "test-project")

        # Test case 2: Multiple errors
        mock_response.json = {
            "errors": [{"message": "Field error"}, {"message": "Syntax error"}],
            "data": None,
        }

        with pytest.raises(
            Exception,
            match="GraphQL query failed with errors: Field error; Syntax error",
        ):
            execute_graphql_query(mock_nautobot_client, "test-project")

        # Test case 3: Error without message field
        mock_response.json = {
            "errors": [{"code": "INVALID_QUERY", "details": "Query is malformed"}],
            "data": None,
        }

        with pytest.raises(Exception, match="GraphQL query failed with errors"):
            execute_graphql_query(mock_nautobot_client, "test-project")

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_handling_of_empty_query_results(self, mock_logger):
        """Test handling of empty query results."""
        # Test case 1: Empty virtual_machines array
        mock_response_empty_vms = Mock()
        mock_response_empty_vms.json = {"data": {"virtual_machines": []}}

        mock_nautobot_client = Mock()
        mock_nautobot_client.session.graphql.query.return_value = (
            mock_response_empty_vms
        )

        result = execute_graphql_query(mock_nautobot_client, "empty-project")

        assert result["data"]["virtual_machines"] == []
        mock_logger.info.assert_called_with(
            "GraphQL query successful. Found %s virtual machine(s) " "for device: %s",
            0,
            "os-empty-project",
        )

        # Test case 2: Missing virtual_machines key
        mock_response_missing_vms = Mock()
        mock_response_missing_vms.json = {"data": {}}

        mock_nautobot_client.session.graphql.query.return_value = (
            mock_response_missing_vms
        )

        result = execute_graphql_query(mock_nautobot_client, "missing-vms-project")

        # Should handle missing key gracefully
        assert result == {"data": {}}

        # Test case 3: VM with empty interfaces
        mock_response_empty_interfaces = Mock()
        mock_response_empty_interfaces.json = {
            "data": {"virtual_machines": [{"interfaces": []}]}
        }

        mock_nautobot_client.session.graphql.query.return_value = (
            mock_response_empty_interfaces
        )

        result = execute_graphql_query(mock_nautobot_client, "empty-interfaces-project")

        assert len(result["data"]["virtual_machines"]) == 1
        assert result["data"]["virtual_machines"][0]["interfaces"] == []
        mock_logger.info.assert_called_with(
            "GraphQL query successful. Found %s virtual machine(s) " "for device: %s",
            1,
            "os-empty-interfaces-project",
        )

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_graphql_query_logging_behavior(self, mock_logger):
        """Test GraphQL query logging behavior."""
        # Mock successful response
        mock_response = Mock()
        mock_response.json = {"data": {"virtual_machines": [{"interfaces": []}]}}

        mock_nautobot_client = Mock()
        mock_nautobot_client.session.graphql.query.return_value = mock_response

        # Execute query
        project_id = "logging-test-project"
        execute_graphql_query(mock_nautobot_client, project_id)

        # Verify debug logging
        mock_logger.debug.assert_any_call(
            "Executing GraphQL query for device: %s", "os-logging-test-project"
        )
        mock_logger.debug.assert_any_call(
            "Query variables: %s", {"device_names": ["os-logging-test-project"]}
        )

        # Verify info logging
        mock_logger.info.assert_called_with(
            "GraphQL query successful. Found %s virtual machine(s) " "for device: %s",
            1,
            "os-logging-test-project",
        )

    def test_validate_and_transform_response_with_valid_data(self):
        """Test validate_and_transform_response with valid GraphQL response data."""
        graphql_response = {
            "data": {
                "virtual_machines": [
                    {
                        "interfaces": [
                            {
                                "name": "N1-lif-A",
                                "ip_addresses": [{"address": "100.127.0.21/29"}],
                                "tagged_vlans": [{"vid": 2002}],
                            },
                            {
                                "name": "N1-lif-B",
                                "ip_addresses": [{"address": "100.127.128.21/29"}],
                                "tagged_vlans": [{"vid": 2002}],
                            },
                        ]
                    }
                ]
            }
        }

        result = validate_and_transform_response(graphql_response)

        assert len(result) == 1
        assert isinstance(result[0], VirtualMachineNetworkInfo)
        assert len(result[0].interfaces) == 2

        # Check first interface
        assert result[0].interfaces[0].name == "N1-lif-A"
        assert result[0].interfaces[0].address == "100.127.0.21/29"
        assert result[0].interfaces[0].vlan == 2002

        # Check second interface
        assert result[0].interfaces[1].name == "N1-lif-B"
        assert result[0].interfaces[1].address == "100.127.128.21/29"
        assert result[0].interfaces[1].vlan == 2002

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_validate_and_transform_response_with_empty_results(self, mock_logger):
        """Test validate_and_transform_response with empty query results."""
        # Test case 1: Empty virtual_machines array
        graphql_response_empty = {"data": {"virtual_machines": []}}

        result = validate_and_transform_response(graphql_response_empty)

        assert result == []
        mock_logger.warning.assert_called_with(
            "No virtual machines found in GraphQL response"
        )

        # Test case 2: Missing virtual_machines key
        graphql_response_missing = {"data": {}}

        result = validate_and_transform_response(graphql_response_missing)

        assert result == []

        # Test case 3: Missing data key
        graphql_response_no_data = {}

        result = validate_and_transform_response(graphql_response_no_data)

        assert result == []

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_validate_and_transform_response_error_propagation(self, mock_logger):
        """Test that validate_and_transform_response propagates validation errors."""
        # GraphQL response with invalid interface data
        graphql_response = {
            "data": {
                "virtual_machines": [
                    {
                        "interfaces": [
                            {
                                "name": "valid-interface",
                                "ip_addresses": [{"address": "192.168.1.10/24"}],
                                "tagged_vlans": [{"vid": 100}],
                            },
                            {
                                "name": "invalid-interface",
                                # No IP addresses - should cause validation error
                                "ip_addresses": [],
                                "tagged_vlans": [{"vid": 200}],
                            },
                        ]
                    }
                ]
            }
        }

        with pytest.raises(ValueError, match="Data validation error"):
            validate_and_transform_response(graphql_response)

        # Verify error logging
        mock_logger.error.assert_called()

    @patch("understack_workflows.main.netapp_configure_net.logger")
    def test_validate_and_transform_response_logging_behavior(self, mock_logger):
        """Test validate_and_transform_response logging behavior."""
        graphql_response = {
            "data": {
                "virtual_machines": [
                    {
                        "interfaces": [
                            {
                                "name": "test-interface",
                                "ip_addresses": [{"address": "192.168.1.10/24"}],
                                "tagged_vlans": [{"vid": 100}],
                            }
                        ]
                    },
                    {
                        "interfaces": [
                            {
                                "name": "test-interface-2",
                                "ip_addresses": [{"address": "192.168.1.11/24"}],
                                "tagged_vlans": [{"vid": 200}],
                            }
                        ]
                    },
                ]
            }
        }

        result = validate_and_transform_response(graphql_response)

        # Verify debug logging for each VM
        mock_logger.debug.assert_any_call(
            "Successfully validated VM with %s interfaces", 1
        )

        # Verify info logging for summary
        mock_logger.info.assert_called_with(
            "Successfully validated %s virtual machine(s)", 2
        )

        assert len(result) == 2


class TestNetappCreateInterfaces:
    """Test cases for netapp_create_interfaces function."""

    def test_netapp_create_interfaces_with_single_interface(self):
        """Test creating NetApp interfaces with single interface configuration."""
        # Mock NetAppManager
        mock_netapp_manager = Mock()

        # Create test data
        interface = InterfaceInfo(name="N1-lif-A", address="100.127.0.21/29", vlan=2002)
        vm_network_info = VirtualMachineNetworkInfo(interfaces=[interface])
        project_id = "test-project-123"

        # Mock NetappIPInterfaceConfig.from_nautobot_response
        with patch(
            "understack_workflows.main.netapp_configure_net.NetappIPInterfaceConfig"
        ) as mock_config_class:
            mock_config = Mock()
            mock_config.name = "N1-lif-A"
            mock_config_class.from_nautobot_response.return_value = [mock_config]

            # Call the function
            netapp_create_interfaces(mock_netapp_manager, vm_network_info, project_id)

            # Verify NetappIPInterfaceConfig.from_nautobot_response was called
            mock_config_class.from_nautobot_response.assert_called_once_with(
                vm_network_info, mock_netapp_manager.config
            )

            # Verify create_lif was called with correct parameters
            mock_netapp_manager.create_lif.assert_called_once_with(
                project_id, mock_config
            )

    def test_netapp_create_interfaces_with_multiple_interfaces(self):
        """Test creating NetApp interfaces with multiple interface configurations."""
        # Mock NetAppManager
        mock_netapp_manager = Mock()

        # Create test data with multiple interfaces
        interfaces = [
            InterfaceInfo(name="N1-lif-A", address="100.127.0.21/29", vlan=2002),
            InterfaceInfo(name="N1-lif-B", address="100.127.128.21/29", vlan=2002),
            InterfaceInfo(name="N2-lif-A", address="100.127.0.22/29", vlan=2002),
            InterfaceInfo(name="N2-lif-B", address="100.127.128.22/29", vlan=2002),
        ]
        vm_network_info = VirtualMachineNetworkInfo(interfaces=interfaces)
        project_id = "test-project-456"

        # Mock NetappIPInterfaceConfig.from_nautobot_response
        with patch(
            "understack_workflows.main.netapp_configure_net.NetappIPInterfaceConfig"
        ) as mock_config_class:
            mock_configs = []
            for interface in interfaces:
                mock_config = Mock()
                mock_config.name = interface.name
                mock_configs.append(mock_config)

            mock_config_class.from_nautobot_response.return_value = mock_configs

            # Call the function
            netapp_create_interfaces(mock_netapp_manager, vm_network_info, project_id)

            # Verify NetappIPInterfaceConfig.from_nautobot_response was called
            mock_config_class.from_nautobot_response.assert_called_once_with(
                vm_network_info, mock_netapp_manager.config
            )

            # Verify create_lif was called for each interface
            assert mock_netapp_manager.create_lif.call_count == 4

            # Verify each call had correct parameters
            for i, call in enumerate(mock_netapp_manager.create_lif.call_args_list):
                assert call.args[0] == project_id
                assert call.args[1] == mock_configs[i]

    def test_netapp_create_interfaces_with_empty_interfaces(self):
        """Test creating NetApp interfaces with empty interface list."""
        # Mock NetAppManager
        mock_netapp_manager = Mock()

        # Create test data with no interfaces
        vm_network_info = VirtualMachineNetworkInfo(interfaces=[])
        project_id = "test-project-empty"

        # Mock NetappIPInterfaceConfig.from_nautobot_response
        with patch(
            "understack_workflows.main.netapp_configure_net.NetappIPInterfaceConfig"
        ) as mock_config_class:
            mock_config_class.from_nautobot_response.return_value = []

            # Call the function
            netapp_create_interfaces(mock_netapp_manager, vm_network_info, project_id)

            # Verify NetappIPInterfaceConfig.from_nautobot_response was called
            mock_config_class.from_nautobot_response.assert_called_once_with(
                vm_network_info, mock_netapp_manager.config
            )

            # Verify create_lif was not called
            mock_netapp_manager.create_lif.assert_not_called()

    def test_netapp_create_interfaces_propagates_netapp_manager_exceptions(self):
        """Test that NetAppManager exceptions are propagated correctly."""
        # Mock NetAppManager that raises exception
        mock_netapp_manager = Mock()
        mock_netapp_manager.create_lif.side_effect = Exception("SVM Not Found")

        # Create test data
        interface = InterfaceInfo(name="N1-lif-A", address="100.127.0.21/29", vlan=2002)
        vm_network_info = VirtualMachineNetworkInfo(interfaces=[interface])
        project_id = "test-project-error"

        # Mock NetappIPInterfaceConfig.from_nautobot_response
        with patch(
            "understack_workflows.main.netapp_configure_net.NetappIPInterfaceConfig"
        ) as mock_config_class:
            mock_config = Mock()
            mock_config.name = "N1-lif-A"
            mock_config_class.from_nautobot_response.return_value = [mock_config]

            # Call the function and expect exception to be propagated
            with pytest.raises(Exception, match="SVM Not Found"):
                netapp_create_interfaces(
                    mock_netapp_manager, vm_network_info, project_id
                )

            # Verify create_lif was called before exception
            mock_netapp_manager.create_lif.assert_called_once_with(
                project_id, mock_config
            )

    def test_netapp_create_interfaces_logs_interface_creation(self):
        """Test that interface creation is properly logged."""
        # Mock NetAppManager
        mock_netapp_manager = Mock()

        # Create test data
        interface = InterfaceInfo(
            name="test-interface", address="192.168.1.10/24", vlan=100
        )
        vm_network_info = VirtualMachineNetworkInfo(interfaces=[interface])
        project_id = "test-project-logging"

        # Mock NetappIPInterfaceConfig.from_nautobot_response
        with patch(
            "understack_workflows.main.netapp_configure_net.NetappIPInterfaceConfig"
        ) as mock_config_class:
            mock_config = Mock()
            mock_config.name = "test-interface"
            mock_config_class.from_nautobot_response.return_value = [mock_config]

            # Mock logger
            with patch(
                "understack_workflows.main.netapp_configure_net.logger"
            ) as mock_logger:
                # Call the function
                netapp_create_interfaces(
                    mock_netapp_manager, vm_network_info, project_id
                )

                # Verify logging was called with correct message
                mock_logger.info.assert_called_once_with(
                    "Creating LIF %s for project %s", "test-interface", project_id
                )

    def test_netapp_create_interfaces_with_realistic_data(self):
        """Test creating NetApp interfaces with realistic interface data."""
        # Mock NetAppManager
        mock_netapp_manager = Mock()

        # Load realistic test data from JSON sample
        sample_data = load_json_sample("nautobot_graphql_vm_response_complex.json")
        vm_data = sample_data["data"]["virtual_machines"][0]
        vm_network_info = VirtualMachineNetworkInfo.from_graphql_vm(vm_data)
        project_id = "12345678123456789abc123456789012"

        # Mock NetappIPInterfaceConfig.from_nautobot_response
        with patch(
            "understack_workflows.main.netapp_configure_net.NetappIPInterfaceConfig"
        ) as mock_config_class:
            # Create mock configs that match the realistic data
            mock_configs = []
            expected_names = ["N1-lif-A", "N1-lif-B", "N2-lif-A", "N2-lif-B"]
            for name in expected_names:
                mock_config = Mock()
                mock_config.name = name
                mock_configs.append(mock_config)

            mock_config_class.from_nautobot_response.return_value = mock_configs

            # Call the function
            netapp_create_interfaces(mock_netapp_manager, vm_network_info, project_id)

            # Verify NetappIPInterfaceConfig.from_nautobot_response was called
            mock_config_class.from_nautobot_response.assert_called_once_with(
                vm_network_info, mock_netapp_manager.config
            )

            # Verify create_lif was called for each interface
            assert mock_netapp_manager.create_lif.call_count == 4

            # Verify each call had correct parameters
            for i, _expected_name in enumerate(expected_names):
                call_args = mock_netapp_manager.create_lif.call_args_list[i]
                assert call_args.args[0] == project_id
                assert call_args.args[1] == mock_configs[i]

    def test_netapp_create_interfaces_return_value(self):
        """Test that netapp_create_interfaces returns None."""
        # Mock NetAppManager
        mock_netapp_manager = Mock()

        # Create test data
        interface = InterfaceInfo(name="N1-lif-A", address="100.127.0.21/29", vlan=2002)
        vm_network_info = VirtualMachineNetworkInfo(interfaces=[interface])
        project_id = "test-project-return"

        # Mock NetappIPInterfaceConfig.from_nautobot_response
        with patch(
            "understack_workflows.main.netapp_configure_net.NetappIPInterfaceConfig"
        ) as mock_config_class:
            mock_config = Mock()
            mock_config.name = "N1-lif-A"
            mock_config_class.from_nautobot_response.return_value = [mock_config]

            # Call the function and verify return value
            result = netapp_create_interfaces(
                mock_netapp_manager, vm_network_info, project_id
            )
            assert result is None


class TestArgumentParserNetappConfigPath:
    """Test cases for the --netapp-config-path argument."""

    def test_netapp_config_path_default_value(self):
        """Test that --netapp-config-path has correct default value."""
        parser = argument_parser()
        args = parser.parse_args(
            ["--project-id", "12345678-1234-5678-9abc-123456789012"]
        )

        assert args.netapp_config_path == "/etc/netapp/netapp_nvme.conf"

    def test_netapp_config_path_custom_value(self):
        """Test that --netapp-config-path accepts custom values."""
        parser = argument_parser()
        custom_path = "/custom/path/to/netapp.conf"
        args = parser.parse_args(
            [
                "--project-id",
                "12345678-1234-5678-9abc-123456789012",
                "--netapp-config-path",
                custom_path,
            ]
        )

        assert args.netapp_config_path == custom_path

    def test_netapp_config_path_various_paths(self):
        """Test that --netapp-config-path accepts various path formats."""
        parser = argument_parser()
        test_paths = [
            "/etc/netapp/config.ini",
            "./local/config.conf",
            "../relative/path/config.cfg",
            "/absolute/path/with/spaces in name.conf",
            "simple_filename.conf",
            "/path/with-dashes_and_underscores.config",
        ]

        for test_path in test_paths:
            args = parser.parse_args(
                [
                    "--project-id",
                    "12345678-1234-5678-9abc-123456789012",
                    "--netapp-config-path",
                    test_path,
                ]
            )
            assert args.netapp_config_path == test_path

    def test_argument_parser_description_updated(self):
        """Test that argument parser description includes NetApp interface creation."""
        parser = argument_parser()
        expected_description = (
            "Query Nautobot for SVM network configuration and create NetApp "
            "interfaces based on project ID"
        )
        assert parser.description == expected_description


class TestMainFunctionWithNetAppManager:
    """Test cases for main function with NetAppManager integration."""

    @patch("understack_workflows.main.netapp_configure_net.NetAppManager")
    @patch("understack_workflows.main.netapp_configure_net.Nautobot")
    @patch("understack_workflows.main.netapp_configure_net.credential")
    @patch("understack_workflows.main.netapp_configure_net.setup_logger")
    def test_main_function_initializes_netapp_manager_with_default_path(
        self,
        mock_setup_logger,
        mock_credential,
        mock_nautobot_class,
        mock_netapp_manager_class,
    ):
        """Test that main function initializes NetAppManager with default config path.

        The main function should properly initialize NetAppManager using the
        default configuration path when no custom path is provided.
        """
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock successful GraphQL response
        mock_response = Mock()
        mock_response.json = load_json_sample(
            "nautobot_graphql_vm_response_single.json"
        )

        # Mock Nautobot client
        mock_nautobot_instance = Mock()
        mock_nautobot_instance.session.graphql.query.return_value = mock_response
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock NetAppManager
        mock_netapp_manager_instance = Mock()
        mock_netapp_manager_class.return_value = mock_netapp_manager_instance

        # Mock sys.argv with default netapp config path
        with patch(
            "sys.argv",
            [
                "netapp_configure_net.py",
                "--project-id",
                "12345678-1234-5678-9abc-123456789012",
            ],
        ):
            with patch("builtins.print"):
                result = main()

        # Verify successful execution
        assert result == 0

        # Verify NetAppManager was initialized with default path
        mock_netapp_manager_class.assert_called_once_with(
            "/etc/netapp/netapp_nvme.conf"
        )

    @patch("understack_workflows.main.netapp_configure_net.NetAppManager")
    @patch("understack_workflows.main.netapp_configure_net.Nautobot")
    @patch("understack_workflows.main.netapp_configure_net.credential")
    @patch("understack_workflows.main.netapp_configure_net.setup_logger")
    def test_main_function_initializes_netapp_manager_with_custom_path(
        self,
        mock_setup_logger,
        mock_credential,
        mock_nautobot_class,
        mock_netapp_manager_class,
    ):
        """Test that main function initializes NetAppManager with custom config path."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock successful GraphQL response
        mock_response = Mock()
        mock_response.json = load_json_sample(
            "nautobot_graphql_vm_response_single.json"
        )

        # Mock Nautobot client
        mock_nautobot_instance = Mock()
        mock_nautobot_instance.session.graphql.query.return_value = mock_response
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock NetAppManager
        mock_netapp_manager_instance = Mock()
        mock_netapp_manager_class.return_value = mock_netapp_manager_instance

        # Mock sys.argv with custom netapp config path
        custom_path = "/custom/netapp/config.conf"
        with patch(
            "sys.argv",
            [
                "netapp_configure_net.py",
                "--project-id",
                "12345678-1234-5678-9abc-123456789012",
                "--netapp-config-path",
                custom_path,
            ],
        ):
            with patch("builtins.print"):
                result = main()

        # Verify successful execution
        assert result == 0

        # Verify NetAppManager was initialized with custom path
        mock_netapp_manager_class.assert_called_once_with(custom_path)

    @patch("understack_workflows.main.netapp_configure_net.NetAppManager")
    @patch("understack_workflows.main.netapp_configure_net.Nautobot")
    @patch("understack_workflows.main.netapp_configure_net.credential")
    @patch("understack_workflows.main.netapp_configure_net.setup_logger")
    def test_main_function_handles_netapp_manager_initialization_error(
        self,
        mock_setup_logger,
        mock_credential,
        mock_nautobot_class,
        mock_netapp_manager_class,
    ):
        """Test that main function handles NetAppManager initialization errors."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock Nautobot client (won't be used due to NetAppManager error)
        mock_nautobot_instance = Mock()
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock NetAppManager to raise initialization error
        mock_netapp_manager_class.side_effect = Exception(
            "NetApp config file not found"
        )

        # Mock sys.argv
        with patch(
            "sys.argv",
            [
                "netapp_configure_net.py",
                "--project-id",
                "12345678-1234-5678-9abc-123456789012",
            ],
        ):
            result = main()

        # Verify exit code 1 for initialization error
        assert result == 1

        # Verify NetAppManager initialization was attempted
        mock_netapp_manager_class.assert_called_once_with(
            "/etc/netapp/netapp_nvme.conf"
        )

    @patch("understack_workflows.main.netapp_configure_net.netapp_create_interfaces")
    @patch("understack_workflows.main.netapp_configure_net.NetAppManager")
    @patch("understack_workflows.main.netapp_configure_net.Nautobot")
    @patch("understack_workflows.main.netapp_configure_net.credential")
    @patch("understack_workflows.main.netapp_configure_net.setup_logger")
    def test_main_function_calls_netapp_create_interfaces(
        self,
        mock_setup_logger,
        mock_credential,
        mock_nautobot_class,
        mock_netapp_manager_class,
        mock_netapp_create_interfaces,
    ):
        """Test that main function calls netapp_create_interfaces through do_action."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock successful GraphQL response
        mock_response = Mock()
        mock_response.json = load_json_sample(
            "nautobot_graphql_vm_response_single.json"
        )

        # Mock Nautobot client
        mock_nautobot_instance = Mock()
        mock_nautobot_instance.session.graphql.query.return_value = mock_response
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock NetAppManager
        mock_netapp_manager_instance = Mock()
        mock_netapp_manager_class.return_value = mock_netapp_manager_instance

        # Mock sys.argv
        project_id = "12345678123456789abc123456789012"  # UUID without dashes
        with patch(
            "sys.argv",
            [
                "netapp_configure_net.py",
                "--project-id",
                "12345678-1234-5678-9abc-123456789012",
            ],
        ):
            with patch("builtins.print"):
                result = main()

        # Verify successful execution
        assert result == 0

        # Verify netapp_create_interfaces was called
        mock_netapp_create_interfaces.assert_called_once()
        call_args = mock_netapp_create_interfaces.call_args

        # Verify the arguments passed to netapp_create_interfaces
        assert (
            call_args.args[0] == mock_netapp_manager_instance
        )  # NetAppManager instance
        assert isinstance(
            call_args.args[1], VirtualMachineNetworkInfo
        )  # VirtualMachineNetworkInfo
        assert call_args.args[2] == project_id  # project_id
