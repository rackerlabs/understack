import json

import pytest

from ironic_understack.portgroup_name_middleware import PORT_CHANNEL_MAX
from ironic_understack.portgroup_name_middleware import PORT_CHANNEL_MIN
from ironic_understack.portgroup_name_middleware import (
    PortgroupNameValidationMiddleware,
)
from ironic_understack.portgroup_name_middleware import validate_portgroup_name


class TestValidatePortgroupName:
    """Tests for the validate_portgroup_name function."""

    def test_valid_name_min_range(self):
        is_valid, error = validate_portgroup_name("node01-port-channel100")
        assert is_valid is True
        assert error is None

    def test_valid_name_max_range(self):
        is_valid, error = validate_portgroup_name("node01-port-channel998")
        assert is_valid is True
        assert error is None

    def test_valid_name_mid_range(self):
        is_valid, error = validate_portgroup_name("server-abc-port-channel500")
        assert is_valid is True
        assert error is None

    def test_invalid_empty_name(self):
        is_valid, error = validate_portgroup_name("")
        assert is_valid is False
        assert "required" in error.lower()

    def test_invalid_none_name(self):
        is_valid, error = validate_portgroup_name(None)
        assert is_valid is False
        assert "required" in error.lower()

    def test_invalid_missing_port_channel(self):
        is_valid, error = validate_portgroup_name("node01")
        assert is_valid is False
        assert "must match format" in error

    def test_invalid_missing_number(self):
        is_valid, error = validate_portgroup_name("node01-port-channel")
        assert is_valid is False
        assert "must match format" in error

    def test_invalid_non_numeric_suffix(self):
        is_valid, error = validate_portgroup_name("node01-port-channelabc")
        assert is_valid is False
        assert "must match format" in error

    def test_invalid_wrong_suffix(self):
        is_valid, error = validate_portgroup_name("node01-port-abc234")
        assert is_valid is False
        assert "must match format" in error

    def test_invalid_number_below_range(self):
        is_valid, error = validate_portgroup_name("node01-port-channel99")
        assert is_valid is False
        assert "99" in error
        assert str(PORT_CHANNEL_MIN) in error
        assert str(PORT_CHANNEL_MAX) in error

    def test_invalid_number_above_range(self):
        is_valid, error = validate_portgroup_name("node01-port-channel999")
        assert is_valid is False
        assert "999" in error
        assert str(PORT_CHANNEL_MIN) in error
        assert str(PORT_CHANNEL_MAX) in error

    def test_invalid_number_zero(self):
        is_valid, error = validate_portgroup_name("node01-port-channel0")
        assert is_valid is False

    def test_invalid_number_very_large(self):
        is_valid, error = validate_portgroup_name("node01-port-channel99999")
        assert is_valid is False


class TestPortgroupNameValidationMiddleware:
    """Tests for the middleware class."""

    @pytest.fixture
    def mock_app(self):
        """Mock WSGI app that returns 200 OK."""

        def app(environ, start_response):
            start_response("200 OK", [("Content-Type", "application/json")])
            return [b'{"status": "ok"}']

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        return PortgroupNameValidationMiddleware(mock_app)

    def test_non_portgroup_request_passes_through(self, middleware):
        """Non-portgroup requests should pass through unchanged."""
        from webob import Request

        req = Request.blank("/v1/nodes")
        req.method = "POST"
        resp = req.get_response(middleware)
        assert resp.status_code == 200

    def test_get_portgroup_passes_through(self, middleware):
        """GET requests should pass through unchanged."""
        from webob import Request

        req = Request.blank("/v1/portgroups")
        req.method = "GET"
        resp = req.get_response(middleware)
        assert resp.status_code == 200

    def test_create_valid_portgroup(self, middleware):
        """POST with valid name should pass through."""
        from webob import Request

        req = Request.blank("/v1/portgroups")
        req.method = "POST"
        req.content_type = "application/json"
        req.body = json.dumps(
            {"name": "node01-port-channel100", "node_uuid": "test-uuid"}
        ).encode()
        resp = req.get_response(middleware)
        assert resp.status_code == 200

    def test_create_invalid_portgroup_rejected(self, middleware):
        """POST with invalid name should return 400."""
        from webob import Request

        req = Request.blank("/v1/portgroups")
        req.method = "POST"
        req.content_type = "application/json"
        req.body = json.dumps(
            {"name": "invalid-name", "node_uuid": "test-uuid"}
        ).encode()
        resp = req.get_response(middleware)
        assert resp.status_code == 400
        assert "must match format" in resp.text

    def test_create_portgroup_number_out_of_range(self, middleware):
        """POST with out-of-range number should return 400."""
        from webob import Request

        req = Request.blank("/v1/portgroups")
        req.method = "POST"
        req.content_type = "application/json"
        req.body = json.dumps(
            {"name": "node01-port-channel20", "node_uuid": "test-uuid"}
        ).encode()
        resp = req.get_response(middleware)
        assert resp.status_code == 400
        assert "20" in resp.text
        assert "100" in resp.text

    def test_patch_valid_name(self, middleware):
        """PATCH with valid name should pass through."""
        from webob import Request

        req = Request.blank("/v1/portgroups/some-uuid")
        req.method = "PATCH"
        req.content_type = "application/json"
        req.body = json.dumps(
            [{"op": "replace", "path": "/name", "value": "node01-port-channel200"}]
        ).encode()
        resp = req.get_response(middleware)
        assert resp.status_code == 200

    def test_patch_invalid_name_rejected(self, middleware):
        """PATCH with invalid name should return 400."""
        from webob import Request

        req = Request.blank("/v1/portgroups/some-uuid")
        req.method = "PATCH"
        req.content_type = "application/json"
        req.body = json.dumps(
            [{"op": "replace", "path": "/name", "value": "bad-name"}]
        ).encode()
        resp = req.get_response(middleware)
        assert resp.status_code == 400

    def test_patch_non_name_field_passes_through(self, middleware):
        """PATCH on non-name fields should pass through."""
        from webob import Request

        req = Request.blank("/v1/portgroups/some-uuid")
        req.method = "PATCH"
        req.content_type = "application/json"
        req.body = json.dumps(
            [{"op": "replace", "path": "/mode", "value": "balance-rr"}]
        ).encode()
        resp = req.get_response(middleware)
        assert resp.status_code == 200

    def test_malformed_json_passes_to_ironic(self, middleware):
        """Malformed JSON should be passed to Ironic to handle."""
        from webob import Request

        req = Request.blank("/v1/portgroups")
        req.method = "POST"
        req.content_type = "application/json"
        req.body = b"not valid json"
        resp = req.get_response(middleware)
        # Should pass through to the app, not fail in middleware
        assert resp.status_code == 200
