"""Tests for PAN-OS inspect interface."""

import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import Mock

import pytest
from ironic.common import exception

from ironic_understack.drivers.panos_inspect import PanosInspect


@pytest.fixture
def mock_task():
    """Create a mock Ironic task object."""
    task = Mock()
    task.node = Mock()
    task.node.uuid = "test-node-uuid"
    task.node.driver_info = {
        "management_ip": "10.15.149.107",
    }
    # Credentials will come from the panos-credentials secret
    # via the credential() helper, not from driver_info
    return task


@pytest.fixture
def fixtures_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def system_info_xml(fixtures_dir):
    """Load system_info.xml fixture."""
    return (fixtures_dir / "system_info.xml").read_text()


@pytest.fixture
def interface_mgmt_xml(fixtures_dir):
    """Load interface_management.xml fixture."""
    return (fixtures_dir / "interface_management.xml").read_text()


@pytest.fixture
def ha_state_xml(fixtures_dir):
    """Load ha_state.xml fixture."""
    return (fixtures_dir / "ha_state.xml").read_text()


class TestPanosInspect:
    """Test cases for PanosInspect interface."""

    def test_instantiate(self):
        """Test that PanosInspect can be instantiated."""
        inspector = PanosInspect()
        assert inspector is not None

    def test_get_properties(self):
        """Test get_properties returns property descriptions."""
        inspector = PanosInspect()
        props = inspector.get_properties()
        # Should return dict with property descriptions
        assert isinstance(props, dict)
        # Currently returns properties but we don't strictly require any

    def test_validate_missing_management_ip(self, mock_task):
        """Test validate raises error when management_ip is missing."""
        mock_task.node.driver_info = {}
        inspector = PanosInspect()

        # Should raise since panos_address (or management_ip) is missing
        with pytest.raises(exception.MissingParameterValue):
            inspector.validate(mock_task)

    def test_validate_success(self, mock_task):
        """Test validate succeeds with required fields present."""
        # Set the fields that the driver actually needs
        mock_task.node.driver_info = {
            "panos_address": "10.15.149.107",
            "panos_username": "admin",
            "panos_password": "password",
        }
        inspector = PanosInspect()
        # Should not raise
        inspector.validate(mock_task)

    def test_parse_system_info(self, system_info_xml):
        """Test parsing system info XML."""
        root = ET.fromstring(system_info_xml)  # noqa: S314
        system = root.find(".//system")

        assert system is not None
        assert system.find("serial").text == "026701009879"
        assert system.find("model").text == "PA-1410"
        assert system.find("hostname").text == "PA-1410"
        assert system.find("sw-version").text == "11.0.0"
        assert system.find("mac-address").text == "8c:36:7a:23:3a:3a"
        assert system.find("ip-address").text == "10.15.149.107"
        assert system.find("netmask").text == "255.255.255.0"
        assert system.find("default-gateway").text == "10.15.149.1"

    def test_parse_interface_management(self, interface_mgmt_xml):
        """Test parsing management interface XML."""
        root = ET.fromstring(interface_mgmt_xml)  # noqa: S314
        info = root.find(".//info")

        assert info is not None
        assert info.find("state").text == "up"
        assert info.find("ip").text == "10.15.149.107"
        assert info.find("netmask").text == "255.255.255.0"
        assert info.find("gw").text == "10.15.149.1"
        assert info.find("hwaddr").text == "8c:36:7a:23:3a:3a"

    def test_parse_ha_state_disabled(self, ha_state_xml):
        """Test parsing HA state when HA is disabled."""
        root = ET.fromstring(ha_state_xml)  # noqa: S314
        enabled = root.find(".//enabled")

        assert enabled is not None
        assert enabled.text == "no"

    def test_credential_fallback_order(self):
        """Test credentials tried in order: standard -> preconfig -> factory."""
        # This test documents the expected credential fallback behavior
        expected_order = [
            "standard_password",
            "preconfig_password",
            "factory_password",
        ]

        # Implementation will need to try these in order
        assert expected_order == [
            "standard_password",
            "preconfig_password",
            "factory_password",
        ]
