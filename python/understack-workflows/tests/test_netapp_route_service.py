"""Tests for NetApp Route Service."""

import ipaddress
from unittest.mock import Mock

import pytest
from netapp_ontap.error import NetAppRestError

from understack_workflows.netapp.exceptions import NetAppManagerError
from understack_workflows.netapp.route_service import RouteService
from understack_workflows.netapp.value_objects import NetappIPInterfaceConfig
from understack_workflows.netapp.value_objects import RouteResult
from understack_workflows.netapp.value_objects import RouteSpec


class TestRouteService:
    """Test cases for RouteService class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock NetApp client."""
        return Mock()

    @pytest.fixture
    def mock_error_handler(self):
        """Create a mock error handler."""
        return Mock()

    @pytest.fixture
    def route_service(self, mock_client, mock_error_handler):
        """Create RouteService instance with mocked dependencies."""
        return RouteService(mock_client, mock_error_handler)

    @pytest.fixture
    def sample_interface_configs(self):
        """Create sample NetappIPInterfaceConfig instances for testing."""
        return [
            NetappIPInterfaceConfig(
                name="N1-lif-A",
                address=ipaddress.IPv4Address("100.127.0.21"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            ),
            NetappIPInterfaceConfig(
                name="N1-lif-B",
                address=ipaddress.IPv4Address("100.127.128.21"),
                network=ipaddress.IPv4Network("100.127.128.16/29"),
                vlan_id=200,
            ),
            NetappIPInterfaceConfig(
                name="N2-lif-A",
                address=ipaddress.IPv4Address("100.127.0.22"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            ),
            NetappIPInterfaceConfig(
                name="N2-lif-B",
                address=ipaddress.IPv4Address("100.127.128.22"),
                network=ipaddress.IPv4Network("100.127.128.16/29"),
                vlan_id=200,
            ),
        ]

    def test_create_routes_from_interfaces_success(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test successful route creation from interface configurations."""
        project_id = "test-project-123"
        expected_svm_name = "os-test-project-123"

        # Mock route creation results
        route_results = [
            RouteResult(
                uuid="route-uuid-1",
                gateway="100.127.0.17",
                destination=ipaddress.IPv4Network("100.126.0.0/17"),
                svm_name=expected_svm_name,
            ),
            RouteResult(
                uuid="route-uuid-2",
                gateway="100.127.128.17",
                destination=ipaddress.IPv4Network("100.126.128.0/17"),
                svm_name=expected_svm_name,
            ),
        ]
        mock_client.create_route.side_effect = route_results

        result = route_service.create_routes_from_interfaces(
            project_id, sample_interface_configs
        )

        # Verify results
        assert len(result) == 2
        assert result == route_results

        # Verify client was called twice (for two unique nexthops)
        assert mock_client.create_route.call_count == 2

        # Verify route specs were created correctly
        call_args_list = mock_client.create_route.call_args_list
        route_specs = [call[0][0] for call in call_args_list]

        # Check first route spec
        assert isinstance(route_specs[0], RouteSpec)
        assert route_specs[0].svm_name == expected_svm_name
        assert route_specs[0].gateway in ["100.127.0.17", "100.127.128.17"]
        assert route_specs[0].destination in [
            ipaddress.IPv4Network("100.126.0.0/17"),
            ipaddress.IPv4Network("100.126.128.0/17"),
        ]

        # Check second route spec
        assert isinstance(route_specs[1], RouteSpec)
        assert route_specs[1].svm_name == expected_svm_name
        assert route_specs[1].gateway in ["100.127.0.17", "100.127.128.17"]
        assert route_specs[1].destination in [
            ipaddress.IPv4Network("100.126.0.0/17"),
            ipaddress.IPv4Network("100.126.128.0/17"),
        ]

        # Verify different gateways were used
        gateways = {spec.gateway for spec in route_specs}
        assert len(gateways) == 2
        assert "100.127.0.17" in gateways
        assert "100.127.128.17" in gateways

        # Verify logging
        mock_error_handler.log_info.assert_called()

    def test_create_routes_from_interfaces_single_route(
        self, route_service, mock_client, mock_error_handler
    ):
        """Test route creation with interfaces that have the same nexthop."""
        project_id = "test-project-456"
        expected_svm_name = "os-test-project-456"

        # Create interfaces with same nexthop (same network)
        interface_configs = [
            NetappIPInterfaceConfig(
                name="N1-lif-A",
                address=ipaddress.IPv4Address("100.127.0.21"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            ),
            NetappIPInterfaceConfig(
                name="N2-lif-A",
                address=ipaddress.IPv4Address("100.127.0.22"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            ),
        ]

        # Mock route creation result
        route_result = RouteResult(
            uuid="route-uuid-1",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
            svm_name=expected_svm_name,
        )
        mock_client.create_route.return_value = route_result

        result = route_service.create_routes_from_interfaces(
            project_id, interface_configs
        )

        # Verify only one route was created (duplicate nexthops eliminated)
        assert len(result) == 1
        assert result[0] == route_result

        # Verify client was called only once
        mock_client.create_route.assert_called_once()

        # Verify route spec
        call_args = mock_client.create_route.call_args[0][0]
        assert isinstance(call_args, RouteSpec)
        assert call_args.svm_name == expected_svm_name
        assert call_args.gateway == "100.127.0.17"
        assert call_args.destination == ipaddress.IPv4Network("100.126.0.0/17")

    def test_create_routes_from_interfaces_empty_list(
        self, route_service, mock_client, mock_error_handler
    ):
        """Test route creation with empty interface configurations list."""
        project_id = "test-project-789"

        result = route_service.create_routes_from_interfaces(project_id, [])

        # Verify no routes were created
        assert len(result) == 0

        # Verify client was not called
        mock_client.create_route.assert_not_called()

        # Verify logging - no logging expected for empty list
        mock_error_handler.log_info.assert_not_called()

    def test_create_routes_from_interfaces_route_creation_error(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test route creation when individual route creation fails."""
        project_id = "test-project-error"

        # Mock route creation failure
        mock_client.create_route.side_effect = Exception("NetApp route creation failed")
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "Operation failed"
        )

        with pytest.raises(NetAppManagerError):
            route_service.create_routes_from_interfaces(
                project_id, sample_interface_configs
            )

        # Verify error handler was called
        mock_error_handler.handle_operation_error.assert_called()

    def test_create_routes_from_interfaces_partial_failure(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test route creation when one route succeeds and another fails."""
        project_id = "test-project-partial"
        expected_svm_name = "os-test-project-partial"

        # Mock first route success, second route failure
        route_result = RouteResult(
            uuid="route-uuid-1",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
            svm_name=expected_svm_name,
        )
        mock_client.create_route.side_effect = [
            route_result,
            Exception("Second route failed"),
        ]
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "Operation failed"
        )

        with pytest.raises(NetAppManagerError):
            route_service.create_routes_from_interfaces(
                project_id, sample_interface_configs
            )

        # Verify both routes were attempted
        assert mock_client.create_route.call_count == 2

        # Verify error handler was called for the failure
        mock_error_handler.handle_operation_error.assert_called()

    def test_extract_unique_nexthops_with_duplicates(
        self, route_service, mock_error_handler, sample_interface_configs
    ):
        """Test unique nexthop extraction with duplicate addresses."""
        result = route_service._extract_unique_nexthops(sample_interface_configs)

        # Should have 2 unique nexthops from 4 interfaces
        assert len(result) == 2
        assert "100.127.0.17" in result
        assert "100.127.128.17" in result

        # Verify logging
        mock_error_handler.log_debug.assert_called()

    def test_extract_unique_nexthops_all_unique(
        self, route_service, mock_error_handler
    ):
        """Test unique nexthop extraction with all unique addresses."""
        interface_configs = [
            NetappIPInterfaceConfig(
                name="N1-lif-A",
                address=ipaddress.IPv4Address("100.127.0.21"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            ),
            NetappIPInterfaceConfig(
                name="N1-lif-B",
                address=ipaddress.IPv4Address("100.127.128.21"),
                network=ipaddress.IPv4Network("100.127.128.16/29"),
                vlan_id=200,
            ),
        ]

        result = route_service._extract_unique_nexthops(interface_configs)

        # Should have 2 unique nexthops from 2 interfaces
        assert len(result) == 2
        assert "100.127.0.17" in result
        assert "100.127.128.17" in result

    def test_extract_unique_nexthops_empty_list(
        self, route_service, mock_error_handler
    ):
        """Test unique nexthop extraction with empty interface configurations list."""
        result = route_service._extract_unique_nexthops([])

        # Should have no nexthops
        assert len(result) == 0

        # Verify logging
        mock_error_handler.log_debug.assert_called()

    def test_extract_unique_nexthops_single_interface(
        self, route_service, mock_error_handler
    ):
        """Test unique nexthop extraction with single interface configuration."""
        interface_configs = [
            NetappIPInterfaceConfig(
                name="N1-lif-A",
                address=ipaddress.IPv4Address("100.127.0.21"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            )
        ]

        result = route_service._extract_unique_nexthops(interface_configs)

        # Should have 1 unique nexthop
        assert len(result) == 1
        assert "100.127.0.17" in result

    def test_svm_name_generation(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test that SVM name is generated correctly using project ID."""
        project_id = "550e8400-e29b-41d4-a716-446655440000"
        expected_svm_name = "os-550e8400-e29b-41d4-a716-446655440000"

        # Mock route creation
        route_result = RouteResult(
            uuid="route-uuid-1",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
            svm_name=expected_svm_name,
        )
        mock_client.create_route.return_value = route_result

        route_service.create_routes_from_interfaces(
            project_id, sample_interface_configs
        )

        # Verify SVM name was used correctly in route specs
        call_args_list = mock_client.create_route.call_args_list
        for call_args in call_args_list:
            route_spec = call_args[0][0]
            assert route_spec.svm_name == expected_svm_name

    def test_route_spec_creation_from_nexthop(
        self, route_service, mock_client, mock_error_handler
    ):
        """Test that RouteSpec is created correctly from nexthop IP addresses."""
        project_id = "test-project"
        expected_svm_name = "os-test-project"

        interface_configs = [
            NetappIPInterfaceConfig(
                name="N1-lif-A",
                address=ipaddress.IPv4Address("100.127.0.21"),
                network=ipaddress.IPv4Network("100.127.0.16/29"),
                vlan_id=100,
            ),
            NetappIPInterfaceConfig(
                name="N1-lif-B",
                address=ipaddress.IPv4Address("100.127.128.21"),
                network=ipaddress.IPv4Network("100.127.128.16/29"),
                vlan_id=200,
            ),
        ]

        # Mock route creation
        mock_client.create_route.side_effect = [
            RouteResult(
                uuid="route-uuid-1",
                gateway="100.127.0.17",
                destination=ipaddress.IPv4Network("100.126.0.0/17"),
                svm_name=expected_svm_name,
            ),
            RouteResult(
                uuid="route-uuid-2",
                gateway="100.127.128.17",
                destination=ipaddress.IPv4Network("100.126.128.0/17"),
                svm_name=expected_svm_name,
            ),
        ]

        route_service.create_routes_from_interfaces(project_id, interface_configs)

        # Verify route specs were created with correct destinations
        call_args_list = mock_client.create_route.call_args_list
        route_specs = [call[0][0] for call in call_args_list]

        # Find specs by gateway to verify destinations
        for spec in route_specs:
            if spec.gateway == "100.127.0.17":
                assert spec.destination == ipaddress.IPv4Network("100.126.0.0/17")
            elif spec.gateway == "100.127.128.17":
                assert spec.destination == ipaddress.IPv4Network("100.126.128.0/17")
            else:
                pytest.fail(f"Unexpected gateway: {spec.gateway}")

    def test_logging_behavior(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test that appropriate logging occurs during route creation."""
        project_id = "test-logging"
        expected_svm_name = "os-test-logging"

        # Mock route creation
        route_results = [
            RouteResult(
                uuid="route-uuid-1",
                gateway="100.127.0.17",
                destination=ipaddress.IPv4Network("100.126.0.0/17"),
                svm_name=expected_svm_name,
            ),
            RouteResult(
                uuid="route-uuid-2",
                gateway="100.127.128.17",
                destination=ipaddress.IPv4Network("100.126.128.0/17"),
                svm_name=expected_svm_name,
            ),
        ]
        mock_client.create_route.side_effect = route_results

        route_service.create_routes_from_interfaces(
            project_id, sample_interface_configs
        )

        # Verify logging calls
        log_info_calls = mock_error_handler.log_info.call_args_list
        log_debug_calls = mock_error_handler.log_debug.call_args_list

        # Should have info logs for: each route creation (no start/completion logs)
        assert len(log_info_calls) >= 2  # 2 routes created

        # Should have debug logs for nexthop extraction
        assert len(log_debug_calls) >= 1

        # Verify specific log messages
        log_messages = [call[0][0] for call in log_info_calls]
        assert any("Created route:" in msg for msg in log_messages)

    def test_create_routes_netapp_rest_error_handling(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test NetAppRestError handling during route creation."""
        project_id = "test-netapp-error"

        # Mock NetAppRestError from client
        netapp_error = NetAppRestError("SVM 'os-test-netapp-error' not found")
        mock_client.create_route.side_effect = netapp_error

        # Mock error handler to raise NetworkOperationError
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "Route creation failed"
        )

        with pytest.raises(NetAppManagerError):
            route_service.create_routes_from_interfaces(
                project_id, sample_interface_configs
            )

        # Verify client was called
        mock_client.create_route.assert_called_once()

        # Verify error handler was called (should be called twice - once for
        # individual route, once for overall operation)
        assert mock_error_handler.handle_operation_error.call_count == 2

        # Check the first call (individual route error)
        first_call = mock_error_handler.handle_operation_error.call_args_list[0]
        assert isinstance(first_call[0][0], NetAppRestError)
        assert "Route creation for nexthop" in first_call[0][1]
        assert first_call[0][2]["project_id"] == "test-netapp-error"
        assert first_call[0][2]["svm_name"] == "os-test-netapp-error"

        # Check the second call (overall operation error)
        second_call = mock_error_handler.handle_operation_error.call_args_list[1]
        assert isinstance(second_call[0][0], NetAppManagerError)
        assert "Route creation for project test-netapp-error" in second_call[0][1]

    def test_create_routes_invalid_svm_error_context(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test error context for invalid SVM during route creation."""
        project_id = "invalid-svm-test"
        expected_svm_name = "os-invalid-svm-test"

        # Mock NetAppRestError for invalid SVM
        netapp_error = NetAppRestError(f"SVM '{expected_svm_name}' does not exist")
        mock_client.create_route.side_effect = netapp_error

        # Mock error handler to raise NetworkOperationError
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "SVM not found"
        )

        with pytest.raises(NetAppManagerError):
            route_service.create_routes_from_interfaces(
                project_id, sample_interface_configs
            )

        # Verify error context includes SVM information (check first call for
        # individual route error)
        first_call = mock_error_handler.handle_operation_error.call_args_list[0]
        assert first_call[0][2]["svm_name"] == expected_svm_name
        assert first_call[0][2]["project_id"] == project_id

    def test_create_routes_error_logging_and_context(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test error logging and context information for route failures."""
        project_id = "error-logging-test"

        # Mock detailed NetAppRestError
        detailed_error = NetAppRestError(
            "Route creation failed: Gateway 192.168.1.1 not reachable"
        )
        mock_client.create_route.side_effect = detailed_error

        # Mock error handler to raise NetworkOperationError
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "Route creation failed"
        )

        with pytest.raises(NetAppManagerError):
            route_service.create_routes_from_interfaces(
                project_id, sample_interface_configs
            )

        # Verify error handler was called with detailed context (check first
        # call for individual route error)
        first_call = mock_error_handler.handle_operation_error.call_args_list[0]
        assert first_call[0][2]["project_id"] == project_id
        assert first_call[0][2]["svm_name"] == "os-error-logging-test"
        assert "nexthop" in first_call[0][2]

        # Check second call for overall operation context
        second_call = mock_error_handler.handle_operation_error.call_args_list[1]
        assert second_call[0][2]["project_id"] == project_id
        assert second_call[0][2]["interface_count"] == 4  # Four interfaces from sample

    def test_create_routes_partial_success_with_error(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test route creation where first route succeeds but second fails."""
        project_id = "partial-success-test"
        expected_svm_name = "os-partial-success-test"

        # Mock first route success, second route failure
        route_result = RouteResult(
            uuid="route-uuid-1",
            gateway="100.127.0.17",
            destination=ipaddress.IPv4Network("100.126.0.0/17"),
            svm_name=expected_svm_name,
        )
        netapp_error = NetAppRestError("Second route creation failed")
        mock_client.create_route.side_effect = [route_result, netapp_error]

        # Mock error handler to raise NetworkOperationError on second call
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "Route creation failed"
        )

        with pytest.raises(NetAppManagerError):
            route_service.create_routes_from_interfaces(
                project_id, sample_interface_configs
            )

        # Verify both routes were attempted
        assert mock_client.create_route.call_count == 2

        # Verify error handler was called for the failure (should be called twice)
        assert mock_error_handler.handle_operation_error.call_count == 2

        # Verify success logging occurred for first route
        log_info_calls = mock_error_handler.log_info.call_args_list
        success_logs = [
            call for call in log_info_calls if "Created route:" in call[0][0]
        ]
        assert len(success_logs) == 1  # Only one successful route

    def test_create_routes_script_termination_behavior(
        self, route_service, mock_client, mock_error_handler, sample_interface_configs
    ):
        """Test that route creation errors cause script termination."""
        project_id = "termination-test"

        # Mock critical NetAppRestError that should terminate script
        critical_error = NetAppRestError(
            "Critical system error: NetApp cluster unavailable"
        )
        mock_client.create_route.side_effect = critical_error

        # Mock error handler to raise exception that should terminate script
        mock_error_handler.handle_operation_error.side_effect = NetAppManagerError(
            "Critical route creation failure"
        )

        # Verify that the exception propagates (would terminate script)
        with pytest.raises(NetAppManagerError, match="Critical route creation failure"):
            route_service.create_routes_from_interfaces(
                project_id, sample_interface_configs
            )

        # Verify error was handled with appropriate context (check first call
        # for individual route error)
        first_call = mock_error_handler.handle_operation_error.call_args_list[0]
        assert "Critical system error" in str(first_call[0][0])
        assert first_call[0][2]["project_id"] == project_id
