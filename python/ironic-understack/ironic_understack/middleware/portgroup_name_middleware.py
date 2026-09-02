r"""Middleware to validate portgroup names for undersync compatibility.

This middleware intercepts portgroup create/update requests and validates
that names follow the required format: {node_name}-port-channel{number}

This is required for undersync to extract port-channel numbers via regex:
    name.to_s[/port-channel(\d+)$/, 1]
"""

import json
import re

import webob
import webob.dec
import webob.exc
from oslo_log import log as logging

LOG = logging.getLogger(__name__)

# Pattern: {anything}-port-channel{number} - captures the number
PORTGROUP_NAME_PATTERN = re.compile(r"^.+-port-channel(\d+)$")

# Valid port-channel number range (inclusive)
PORT_CHANNEL_MIN = 100
PORT_CHANNEL_MAX = 998


def validate_portgroup_name(name):
    """Validate portgroup name follows the required format.

    :param name: The portgroup name to validate.
    :returns: tuple (is_valid, error_message)
    """
    if not name:
        return False, "Portgroup name is required and cannot be empty."

    match = PORTGROUP_NAME_PATTERN.match(name)
    if not match:
        return False, (
            f"Portgroup name '{name}' must match format "
            "'{node_name}-port-channel{{number}}' "
            "(e.g., 'server01-port-channel100')"
        )

    port_channel_num = int(match.group(1))
    if not (PORT_CHANNEL_MIN <= port_channel_num <= PORT_CHANNEL_MAX):
        return False, (
            f"Portgroup name '{name}' has invalid port-channel number "
            f"{port_channel_num}. Must be between {PORT_CHANNEL_MIN} "
            f"and {PORT_CHANNEL_MAX} (inclusive)."
        )

    return True, None


class PortgroupNameValidationMiddleware:
    """WSGI middleware that validates portgroup names.

    Intercepts POST /v1/portgroups and PATCH /v1/portgroups/{id} requests
    to validate that portgroup names match the required format.
    """

    def __init__(self, app):
        self.app = app

    @webob.dec.wsgify
    def __call__(self, req):
        # Only check portgroup endpoints
        if not self._is_portgroup_request(req):
            return req.get_response(self.app)

        # Check POST (create) requests
        if req.method == "POST" and req.path_info.rstrip("/") == "/v1/portgroups":
            return self._validate_create(req)

        # Check PATCH (update) requests
        if req.method == "PATCH" and self._is_portgroup_patch(req.path_info):
            return self._validate_patch(req)

        return req.get_response(self.app)

    def _is_portgroup_request(self, req):
        """Check if this is a portgroup-related request."""
        return "/portgroups" in req.path_info

    def _is_portgroup_patch(self, path):
        """Check if this is a PATCH to a specific portgroup."""
        # Matches /v1/portgroups/{uuid_or_name}
        pattern = r"^/v1/portgroups/[^/]+$"
        return bool(re.match(pattern, path.rstrip("/")))

    def _validate_create(self, req):
        """Validate portgroup name on create."""
        try:
            body = json.loads(req.body)
        except (json.JSONDecodeError, ValueError):
            # Let Ironic handle malformed JSON
            return req.get_response(self.app)

        name = body.get("name")
        is_valid, error_msg = validate_portgroup_name(name)
        if not is_valid:
            LOG.warning("Rejecting portgroup creation with invalid name: %s", name)
            return self._error_response(req, error_msg)

        return req.get_response(self.app)

    def _validate_patch(self, req):
        """Validate portgroup name on update."""
        try:
            patch = json.loads(req.body)
        except (json.JSONDecodeError, ValueError):
            # Let Ironic handle malformed JSON
            return req.get_response(self.app)

        # Look for name changes in the patch
        for op in patch:
            if op.get("path") == "/name" and op.get("op") in ("add", "replace"):
                name = op.get("value")
                is_valid, error_msg = validate_portgroup_name(name)
                if not is_valid:
                    LOG.warning(
                        "Rejecting portgroup update with invalid name: %s", name
                    )
                    return self._error_response(req, error_msg)

        return req.get_response(self.app)

    def _error_response(self, req, message):
        """Return a 400 Bad Request response."""
        error_body = {
            "error_message": json.dumps(
                {"faultstring": message, "faultcode": "Client", "debuginfo": None}
            )
        }
        return webob.Response(
            status=400,
            content_type="application/json",
            body=json.dumps(error_body).encode("utf-8"),
        )


def factory(global_conf, **local_conf):
    """Paste deploy factory function."""

    def filter(app):
        return PortgroupNameValidationMiddleware(app)

    return filter
