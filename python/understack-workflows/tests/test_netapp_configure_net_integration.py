import argparse
import json
import pathlib
from contextlib import nullcontext
from unittest.mock import Mock, patch

import pytest

from understack_workflows.main.netapp_configure_net import VIRTUAL_MACHINES_QUERY


def load_json_sample(filename: str) -> dict:
    """Load JSON sample data from the json_samples directory."""
    here = pathlib.Path(__file__).parent
    sample_path = here / "json_samples" / filename
    with sample_path.open("r") as f:
        return json.load(f)


class TestIntegrationTests:
    """Integration tests for complete script execution with mock Nautobot responses."""

    @patch('understack_workflows.main.netapp_configure_net.Nautobot')
    @patch('understack_workflows.main.netapp_configure_net.credential')
    @patch('understack_workflows.main.netapp_configure_net.setup_logger')
    def test_complete_script_execution_with_mock_nautobot_responses(self, mock_setup_logger, mock_credential, mock_nautobot_class):
        """Test complete script execution with mock Nautobot responses."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock successful GraphQL response
        mock_response = Mock()
        mock_response.json = load_json_sample("nautobot_graphql_vm_response_single.json")

        # Mock Nautobot client
        mock_nautobot_instance = Mock()
        mock_nautobot_instance.session.graphql.query.return_value = mock_response
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock sys.argv for argument parsing
        with patch('sys.argv', ['netapp_configure_net.py', '--project-id', '12345678-1234-5678-9abc-123456789012']):
            with patch('builtins.print') as mock_print:
                result = main()

        # Verify successful execution
        assert result == 0

        # Verify Nautobot client was created with correct parameters
        # Note: logger is created at module import time, so we just verify the call was made
        mock_nautobot_class.assert_called_once()
        call_args = mock_nautobot_class.call_args
        assert call_args[0][0] == "http://nautobot-default.nautobot.svc.cluster.local"
        assert call_args[0][1] == "test-token"
        assert 'logger' in call_args[1]

        # Verify GraphQL query was executed
        mock_nautobot_instance.session.graphql.query.assert_called_once_with(
            query=VIRTUAL_MACHINES_QUERY,
            variables={"device_names": ["os-12345678123456789abc123456789012"]}
        )

        # Verify output was printed
        mock_print.assert_called_once()
        printed_output = mock_print.call_args[0][0]

        # Parse the printed JSON to verify structure
        import json
        output_data = json.loads(printed_output)
        assert "data" in output_data
        assert "virtual_machines" in output_data["data"]
        assert len(output_data["data"]["virtual_machines"]) == 1
        assert len(output_data["data"]["virtual_machines"][0]["interfaces"]) == 2

    @patch('understack_workflows.main.netapp_configure_net.Nautobot')
    @patch('understack_workflows.main.netapp_configure_net.credential')
    @patch('understack_workflows.main.netapp_configure_net.setup_logger')
    def test_output_format_validation_structured_data(self, mock_setup_logger, mock_credential, mock_nautobot_class):
        """Test output format validation for structured data."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock complex GraphQL response with multiple interfaces
        mock_response = Mock()
        mock_response.json = load_json_sample("nautobot_graphql_vm_response_complex.json")

        # Mock Nautobot client
        mock_nautobot_instance = Mock()
        mock_nautobot_instance.session.graphql.query.return_value = mock_response
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock sys.argv
        with patch('sys.argv', ['netapp_configure_net.py', '--project-id', 'abcdef12-3456-7890-abcd-ef1234567890']):
            with patch('builtins.print') as mock_print:
                result = main()

        # Verify successful execution
        assert result == 0

        # Verify output was printed
        mock_print.assert_called_once()
        printed_output = mock_print.call_args[0][0]

        # Parse and validate the JSON structure
        import json
        output_data = json.loads(printed_output)

        # Validate top-level structure
        assert "data" in output_data
        assert "virtual_machines" in output_data["data"]
        assert len(output_data["data"]["virtual_machines"]) == 1

        # Validate virtual machine structure
        vm = output_data["data"]["virtual_machines"][0]
        assert "interfaces" in vm
        assert len(vm["interfaces"]) == 4

        # Validate each interface structure
        expected_interfaces = [
            ("N1-lif-A", "100.127.0.21/29", 2002),
            ("N1-lif-B", "100.127.128.21/29", 2002),
            ("N2-lif-A", "100.127.0.22/29", 2002),
            ("N2-lif-B", "100.127.128.22/29", 2002),
        ]

        for i, (expected_name, expected_address, expected_vlan) in enumerate(expected_interfaces):
            interface = vm["interfaces"][i]
            assert "name" in interface
            assert "ip_addresses" in interface
            assert "tagged_vlans" in interface

            assert interface["name"] == expected_name
            assert len(interface["ip_addresses"]) == 1
            assert interface["ip_addresses"][0]["address"] == expected_address
            assert len(interface["tagged_vlans"]) == 1
            assert interface["tagged_vlans"][0]["vid"] == expected_vlan

    @patch('understack_workflows.main.netapp_configure_net.Nautobot')
    @patch('understack_workflows.main.netapp_configure_net.credential')
    @patch('understack_workflows.main.netapp_configure_net.setup_logger')
    def test_exit_code_scenario_connection_error(self, mock_setup_logger, mock_credential, mock_nautobot_class):
        """Test exit code 1 for connection errors."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock Nautobot client to raise connection error
        mock_nautobot_class.side_effect = Exception("Connection failed")

        # Mock sys.argv
        with patch('sys.argv', ['netapp_configure_net.py', '--project-id', '11111111-2222-3333-4444-555555555555']):
            result = main()

        # Verify exit code 1 for connection error
        assert result == 1

    @patch('understack_workflows.main.netapp_configure_net.Nautobot')
    @patch('understack_workflows.main.netapp_configure_net.credential')
    @patch('understack_workflows.main.netapp_configure_net.setup_logger')
    def test_exit_code_scenario_graphql_error(self, mock_setup_logger, mock_credential, mock_nautobot_class):
        """Test exit code 2 for GraphQL query errors."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock GraphQL error response
        mock_response = Mock()
        mock_response.json = load_json_sample("nautobot_graphql_vm_response_error.json")

        # Mock Nautobot client
        mock_nautobot_instance = Mock()
        mock_nautobot_instance.session.graphql.query.return_value = mock_response
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock sys.argv
        with patch('sys.argv', ['netapp_configure_net.py', '--project-id', '22222222-3333-4444-5555-666666666666']):
            result = main()

        # Verify exit code 2 for GraphQL error
        assert result == 2

    @patch('understack_workflows.main.netapp_configure_net.Nautobot')
    @patch('understack_workflows.main.netapp_configure_net.credential')
    @patch('understack_workflows.main.netapp_configure_net.setup_logger')
    def test_exit_code_scenario_data_validation_error(self, mock_setup_logger, mock_credential, mock_nautobot_class):
        """Test exit code 3 for data validation errors."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock GraphQL response with invalid interface data (multiple IP addresses)
        mock_response = Mock()
        mock_response.json = load_json_sample("nautobot_graphql_vm_response_invalid_multiple_ips.json")

        # Mock Nautobot client
        mock_nautobot_instance = Mock()
        mock_nautobot_instance.session.graphql.query.return_value = mock_response
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock sys.argv
        with patch('sys.argv', ['netapp_configure_net.py', '--project-id', '33333333-4444-5555-6666-777777777777']):
            result = main()

        # Verify exit code 3 for data validation error
        assert result == 3

    @patch('understack_workflows.main.netapp_configure_net.Nautobot')
    @patch('understack_workflows.main.netapp_configure_net.credential')
    @patch('understack_workflows.main.netapp_configure_net.setup_logger')
    def test_exit_code_scenario_success_with_empty_results(self, mock_setup_logger, mock_credential, mock_nautobot_class):
        """Test exit code 0 for successful execution with empty results."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "test-token"

        # Mock GraphQL response with no virtual machines
        mock_response = Mock()
        mock_response.json = load_json_sample("nautobot_graphql_vm_response_empty.json")

        # Mock Nautobot client
        mock_nautobot_instance = Mock()
        mock_nautobot_instance.session.graphql.query.return_value = mock_response
        mock_nautobot_class.return_value = mock_nautobot_instance

        # Mock sys.argv
        with patch('sys.argv', ['netapp_configure_net.py', '--project-id', '44444444-5555-6666-7777-888888888888']):
            with patch('builtins.print') as mock_print:
                result = main()

        # Verify exit code 0 for successful execution (even with empty results)
        assert result == 0

        # Verify output was still printed (empty results)
        mock_print.assert_called_once()
        printed_output = mock_print.call_args[0][0]

        # Parse and validate the JSON structure
        import json
        output_data = json.loads(printed_output)
        assert "data" in output_data
        assert "virtual_machines" in output_data["data"]
        assert len(output_data["data"]["virtual_machines"]) == 0

    @patch('understack_workflows.main.netapp_configure_net.Nautobot')
    @patch('understack_workflows.main.netapp_configure_net.credential')
    @patch('understack_workflows.main.netapp_configure_net.setup_logger')
    def test_end_to_end_workflow_with_various_input_combinations(self, mock_setup_logger, mock_credential, mock_nautobot_class):
        """Test end-to-end workflow with various input combinations."""
        from understack_workflows.main.netapp_configure_net import main

        # Mock logger
        mock_logger = Mock()
        mock_setup_logger.return_value = mock_logger

        # Mock credential function
        mock_credential.return_value = "fallback-token"

        # Test cases with different input combinations
        test_cases = [
            {
                "name": "minimal_args",
                "argv": ['netapp_configure_net.py', '--project-id', '55555555-6666-7777-8888-999999999999'],
                "expected_url": "http://nautobot-default.nautobot.svc.cluster.local",
                "expected_token": "fallback-token",
                "expected_device": "os-55555555666677778888999999999999"
            },
            {
                "name": "custom_url_only",
                "argv": ['netapp_configure_net.py', '--project-id', '66666666-7777-8888-9999-aaaaaaaaaaaa', '--nautobot_url', 'https://custom.nautobot.com'],
                "expected_url": "https://custom.nautobot.com",
                "expected_token": "fallback-token",
                "expected_device": "os-66666666777788889999aaaaaaaaaaaa"
            },
            {
                "name": "all_custom_args",
                "argv": ['netapp_configure_net.py', '--project-id', '77777777-8888-9999-aaaa-bbbbbbbbbbbb', '--nautobot_url', 'https://full.custom.com', '--nautobot_token', 'full-custom-token'],
                "expected_url": "https://full.custom.com",
                "expected_token": "full-custom-token",
                "expected_device": "os-7777777788889999aaaabbbbbbbbbbbb"
            }
        ]

        for test_case in test_cases:
            # Reset mocks for each test case
            mock_nautobot_class.reset_mock()
            mock_credential.reset_mock()

            # Mock successful GraphQL response (use single interface sample)
            mock_response = Mock()
            sample_data = load_json_sample("nautobot_graphql_vm_response_single.json")
            # Customize the interface name for this test case
            sample_data["data"]["virtual_machines"][0]["interfaces"][0]["name"] = f"interface-{test_case['name']}"
            sample_data["data"]["virtual_machines"][0]["interfaces"][1]["name"] = f"interface-{test_case['name']}-B"
            mock_response.json = sample_data

            # Mock Nautobot client
            mock_nautobot_instance = Mock()
            mock_nautobot_instance.session.graphql.query.return_value = mock_response
            mock_nautobot_class.return_value = mock_nautobot_instance

            # Execute test case
            with patch('sys.argv', test_case["argv"]):
                with patch('builtins.print') as mock_print:
                    result = main()

            # Verify successful execution
            assert result == 0, f"Test case '{test_case['name']}' failed with exit code {result}"

            # Verify Nautobot client was created with expected parameters
            # Note: logger is created at module import time, so we just verify the call was made
            mock_nautobot_class.assert_called_once()
            call_args = mock_nautobot_class.call_args
            assert call_args[0][0] == test_case["expected_url"]
            assert call_args[0][1] == test_case["expected_token"]
            assert 'logger' in call_args[1]

            # Verify GraphQL query was executed with correct device name
            mock_nautobot_instance.session.graphql.query.assert_called_once_with(
                query=VIRTUAL_MACHINES_QUERY,
                variables={"device_names": [test_case["expected_device"]]}
            )

            # Verify output was printed
            mock_print.assert_called_once()

            # Verify credential function usage
            if "--nautobot_token" in test_case["argv"]:
                mock_credential.assert_not_called()
            else:
                mock_credential.assert_called_once_with("nb-token", "token")
