"""Tests for openstack_oslo_event functionality."""

import argparse
import json
import tempfile
from io import StringIO
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from understack_workflows.main.openstack_oslo_event import _EXIT_HANDLER_ERROR
from understack_workflows.main.openstack_oslo_event import _EXIT_NO_EVENT_HANDLER
from understack_workflows.main.openstack_oslo_event import _EXIT_PARSE_ERROR
from understack_workflows.main.openstack_oslo_event import _EXIT_SUCCESS
from understack_workflows.main.openstack_oslo_event import ClientInitializationError
from understack_workflows.main.openstack_oslo_event import EventParseError
from understack_workflows.main.openstack_oslo_event import EventValidationError
from understack_workflows.main.openstack_oslo_event import argument_parser
from understack_workflows.main.openstack_oslo_event import initialize_clients
from understack_workflows.main.openstack_oslo_event import main
from understack_workflows.main.openstack_oslo_event import read_event
from understack_workflows.main.openstack_oslo_event import validate_event


class TestArgumentParser:
    """Test argument parser functionality."""

    def test_argument_parser_basic(self):
        """Test basic argument parser creation."""
        parser = argument_parser()
        assert isinstance(parser, argparse.ArgumentParser)
        assert parser.description == "OpenStack Event Receiver"

    def test_argument_parser_with_args(self):
        """Test argument parser with various arguments."""
        parser = argument_parser()

        # Test with minimal args
        args = parser.parse_args(["--nautobot_url", "http://test.com"])
        assert args.nautobot_url == "http://test.com"

        # Test with all args
        args = parser.parse_args(
            [
                "--os-cloud",
                "test-cloud",
                "--file",
                "test.json",
                "--nautobot_url",
                "http://test.com",
                "--nautobot_token",
                "test-token",
            ]
        )
        assert args.os_cloud == "test-cloud"
        assert str(args.file) == "test.json"
        assert args.nautobot_url == "http://test.com"
        assert args.nautobot_token == "test-token"


class TestReadEvent:
    """Test event reading functionality."""

    def test_read_event_from_file(self):
        """Test reading event from file."""
        test_event = {"event_type": "test.event", "data": "test"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_event, f)
            f.flush()

            result = read_event(f.name)
            assert result == test_event

    def test_read_event_from_stdin(self):
        """Test reading event from stdin."""
        test_event = {"event_type": "test.event", "data": "test"}
        test_json = json.dumps(test_event)

        with patch("sys.stdin", StringIO(test_json)):
            result = read_event(None)
            assert result == test_event

    def test_read_event_invalid_json(self):
        """Test reading invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json")
            f.flush()

            with pytest.raises(EventParseError):
                read_event(f.name)

    def test_read_event_file_not_found(self):
        """Test reading from non-existent file."""
        with pytest.raises(EventParseError):
            read_event("nonexistent.json")

    def test_read_event_stdin_invalid_json(self):
        """Test reading invalid JSON from stdin."""
        with patch("sys.stdin", StringIO("invalid json")):
            with pytest.raises(EventParseError):
                read_event(None)


class TestValidateEvent:
    """Test event validation functionality."""

    def test_validate_event_basic(self):
        """Test basic event validation."""
        event = {"event_type": "test.event"}
        result = validate_event(event)
        assert result == "test.event"

    def test_validate_event_with_payload(self):
        """Test event validation with payload data."""
        event = {"event_type": "test.event", "payload": {"data": "test"}}
        result = validate_event(event)
        assert result == "test.event"

    def test_validate_event_no_event_type(self):
        """Test validation with missing event_type."""
        with pytest.raises(
            EventValidationError, match="Event must contain 'event_type' field"
        ):
            validate_event({"data": "test"})

    def test_validate_event_non_string_event_type(self):
        """Test validation with non-string event_type."""
        with pytest.raises(EventValidationError, match="Event type must be a string"):
            validate_event({"event_type": 123})

    def test_validate_event_empty_event_type(self):
        """Test validation with empty event_type."""
        event = {"event_type": ""}
        with pytest.raises(
            EventValidationError, match="Event must contain 'event_type' field"
        ):
            validate_event(event)

    def test_validate_event_none_event_type(self):
        """Test validation with None event_type."""
        event = {"event_type": None}
        with pytest.raises(
            EventValidationError, match="Event must contain 'event_type' field"
        ):
            validate_event(event)


class TestInitializeClients:
    """Test client initialization functionality."""

    @patch("understack_workflows.main.openstack_oslo_event.get_openstack_client")
    @patch("understack_workflows.main.openstack_oslo_event.pynautobot.api")
    @patch("understack_workflows.main.openstack_oslo_event.credential")
    def test_initialize_clients_success(
        self, mock_credential, mock_nautobot_api, mock_get_openstack_client
    ):
        """Test successful client initialization."""
        # Mock the clients
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_get_openstack_client.return_value = mock_conn
        mock_nautobot_api.return_value = mock_nautobot
        mock_credential.return_value = "test-token"

        # Create args
        args = argparse.Namespace(
            os_cloud="test-cloud", nautobot_url="http://test.com", nautobot_token=None
        )

        conn, nautobot = initialize_clients(args)

        assert conn == mock_conn
        assert nautobot == mock_nautobot
        mock_get_openstack_client.assert_called_once_with(cloud="test-cloud")
        mock_nautobot_api.assert_called_once_with("http://test.com", token="test-token")  # noqa: S106

    @patch("understack_workflows.main.openstack_oslo_event.get_openstack_client")
    def test_initialize_clients_openstack_error(self, mock_get_openstack_client):
        """Test OpenStack client initialization error."""
        mock_get_openstack_client.side_effect = Exception("OpenStack error")

        args = argparse.Namespace(os_cloud="test-cloud")

        with pytest.raises(
            ClientInitializationError, match="Failed to initialize OpenStack client"
        ):
            initialize_clients(args)

    @patch("understack_workflows.main.openstack_oslo_event.get_openstack_client")
    @patch("understack_workflows.main.openstack_oslo_event.pynautobot.api")
    def test_initialize_clients_nautobot_error(
        self, mock_nautobot_api, mock_get_openstack_client
    ):
        """Test Nautobot client initialization error."""
        mock_get_openstack_client.return_value = Mock()
        mock_nautobot_api.side_effect = Exception("Nautobot error")

        args = argparse.Namespace(
            os_cloud="test-cloud",
            nautobot_url="http://test.com",
            nautobot_token="test-token",  # noqa: S106
        )

        with pytest.raises(
            ClientInitializationError, match="Failed to initialize Nautobot client"
        ):
            initialize_clients(args)


class TestMainFunction:
    """Test main function functionality."""

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.read_event")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_main_success(
        self, mock_argument_parser, mock_read_event, mock_initialize_clients
    ):
        """Test successful main function execution."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock event reading
        test_event = {"event_type": "baremetal.port.create.end", "data": "test"}
        mock_read_event.return_value = test_event

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Mock event handler
        mock_handler = Mock(return_value=0)
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"baremetal.port.create.end": mock_handler},
        ):
            result = main()

        assert result == _EXIT_SUCCESS
        mock_handler.assert_called_once_with(mock_conn, mock_nautobot, test_event)

    @patch("understack_workflows.main.openstack_oslo_event.read_event")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_main_validation_error(self, mock_argument_parser, mock_read_event):
        """Test main function with validation error."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock event reading - invalid event
        test_event = {"data": "test"}  # No event_type
        mock_read_event.return_value = test_event

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == _EXIT_PARSE_ERROR

    @patch("understack_workflows.main.openstack_oslo_event.read_event")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_main_no_event_handler(self, mock_argument_parser, mock_read_event):
        """Test main function with no event handler."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock event reading
        test_event = {"event_type": "unsupported.event", "data": "test"}
        mock_read_event.return_value = test_event

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == _EXIT_NO_EVENT_HANDLER

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.read_event")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_main_handler_error(
        self, mock_argument_parser, mock_read_event, mock_initialize_clients
    ):
        """Test main function with event handler error."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock event reading
        test_event = {"event_type": "baremetal.port.create.end", "data": "test"}
        mock_read_event.return_value = test_event

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Mock event handler that raises exception
        mock_handler = Mock(side_effect=Exception("Handler error"))
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"baremetal.port.create.end": mock_handler},
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == _EXIT_HANDLER_ERROR

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.read_event")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_main_with_payload(
        self, mock_argument_parser, mock_read_event, mock_initialize_clients
    ):
        """Test main function with payload data."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock event reading - event with payload
        test_event = {
            "event_type": "baremetal.port.create.end",
            "payload": {"data": "test"},
        }
        mock_read_event.return_value = test_event

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Mock event handler
        mock_handler = Mock(return_value=0)
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"baremetal.port.create.end": mock_handler},
        ):
            result = main()

        assert result == _EXIT_SUCCESS
        mock_handler.assert_called_once_with(mock_conn, mock_nautobot, test_event)


class TestIntegrationWithEventHandlers:
    """Test integration with various event handlers."""

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_integration_port_create_event(
        self, mock_argument_parser, mock_initialize_clients
    ):
        """Test integration with port create event handler."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Use real event data - extract the oslo.message content
        with open("tests/json_samples/baremetal-port-create-end.json") as f:
            oslo_wrapper = json.load(f)
            test_event = json.loads(oslo_wrapper["oslo.message"])

        # Mock the port event handler by patching the event handlers dict
        mock_handler = Mock(return_value=0)
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"baremetal.port.create.end": mock_handler},
        ):
            with patch(
                "understack_workflows.main.openstack_oslo_event.read_event",
                return_value=test_event,
            ):
                result = main()

        assert result == _EXIT_SUCCESS
        mock_handler.assert_called_once_with(mock_conn, mock_nautobot, test_event)

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_integration_port_delete_event(
        self, mock_argument_parser, mock_initialize_clients
    ):
        """Test integration with port delete event handler."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Use real event data - extract the oslo.message content
        with open("tests/json_samples/baremetal-port-delete-end.json") as f:
            oslo_wrapper = json.load(f)
            test_event = json.loads(oslo_wrapper["oslo.message"])

        # Mock the port event handler by patching the event handlers dict
        mock_handler = Mock(return_value=0)
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"baremetal.port.delete.end": mock_handler},
        ):
            with patch(
                "understack_workflows.main.openstack_oslo_event.read_event",
                return_value=test_event,
            ):
                result = main()

        assert result == _EXIT_SUCCESS
        mock_handler.assert_called_once_with(mock_conn, mock_nautobot, test_event)

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_integration_keystone_project_created_event(
        self, mock_argument_parser, mock_initialize_clients
    ):
        """Test integration with keystone project created event handler."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Use real event data - extract the oslo.message content
        with open("tests/json_samples/keystone-project-created.json") as f:
            oslo_wrapper = json.load(f)
            test_event = json.loads(oslo_wrapper["oslo.message"])

        # Mock the keystone project event handler by patching the event handlers dict
        mock_handler = Mock(return_value=0)
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"identity.project.created": mock_handler},
        ):
            with patch(
                "understack_workflows.main.openstack_oslo_event.read_event",
                return_value=test_event,
            ):
                result = main()

        assert result == _EXIT_SUCCESS
        mock_handler.assert_called_once_with(mock_conn, mock_nautobot, test_event)

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_integration_keystone_project_created_handler_success(
        self, mock_argument_parser, mock_initialize_clients
    ):
        """Test success path with keystone project created event handler."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Use real event data - extract the oslo.message content
        with open("tests/json_samples/keystone-project-created.json") as f:
            oslo_wrapper = json.load(f)
            test_event = json.loads(oslo_wrapper["oslo.message"])

        # Mock the keystone project event handler by patching the event handlers dict
        mock_handler = Mock(return_value=0)
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"identity.project.created": mock_handler},
        ):
            with patch(
                "understack_workflows.main.openstack_oslo_event.read_event",
                return_value=test_event,
            ):
                result = main()

        assert result == _EXIT_SUCCESS
        mock_handler.assert_called_once_with(mock_conn, mock_nautobot, test_event)

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_integration_keystone_project_created_handler_failure(
        self, mock_argument_parser, mock_initialize_clients
    ):
        """Test integration when keystone project created handler fails."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Use real event data - extract the oslo.message content
        with open("tests/json_samples/keystone-project-created.json") as f:
            oslo_wrapper = json.load(f)
            test_event = json.loads(oslo_wrapper["oslo.message"])

        # Mock the keystone project event handler to raise an exception
        mock_handler = Mock(side_effect=Exception("Handler failed"))
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"identity.project.created": mock_handler},
        ):
            with patch(
                "understack_workflows.main.openstack_oslo_event.read_event",
                return_value=test_event,
            ):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == _EXIT_HANDLER_ERROR

        mock_handler.assert_called_once_with(mock_conn, mock_nautobot, test_event)

    @patch("understack_workflows.main.openstack_oslo_event.initialize_clients")
    @patch("understack_workflows.main.openstack_oslo_event.argument_parser")
    def test_integration_keystone_project_created_event_validation(
        self, mock_argument_parser, mock_initialize_clients
    ):
        """Test that keystone project created event passes validation."""
        # Mock argument parser
        mock_parser = Mock()
        mock_args = Mock()
        mock_args.file = None
        mock_parser.parse_args.return_value = mock_args
        mock_argument_parser.return_value = mock_parser

        # Mock client initialization
        mock_conn = Mock()
        mock_nautobot = Mock()
        mock_initialize_clients.return_value = (mock_conn, mock_nautobot)

        # Use real event data - extract the oslo.message content
        with open("tests/json_samples/keystone-project-created.json") as f:
            oslo_wrapper = json.load(f)
            test_event = json.loads(oslo_wrapper["oslo.message"])

        # Verify the event structure
        assert test_event["event_type"] == "identity.project.created"
        assert "payload" in test_event
        assert "target" in test_event["payload"]
        assert "id" in test_event["payload"]["target"]

        # Mock the handler to verify it gets called with correct data
        mock_handler = Mock(return_value=0)
        with patch(
            "understack_workflows.main.openstack_oslo_event._event_handlers",
            {"identity.project.created": mock_handler},
        ):
            with patch(
                "understack_workflows.main.openstack_oslo_event.read_event",
                return_value=test_event,
            ):
                result = main()

        assert result == _EXIT_SUCCESS
        mock_handler.assert_called_once_with(mock_conn, mock_nautobot, test_event)

        # Verify the handler was called with the expected project ID
        call_args = mock_handler.call_args[0]
        event_data = call_args[2]  # Third argument is the event data
        assert (
            event_data["payload"]["target"]["id"] == "148f2f86b96440a1ba0934f837b2c77b"
        )
