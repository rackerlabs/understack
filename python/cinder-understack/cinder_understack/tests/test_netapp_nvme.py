"""Tests for NetApp NVMe connector translation."""

from unittest import TestCase
from unittest import mock

from cinder_understack import netapp_nvme


class TestNetAppNVMeDriver(TestCase):
    """Tests for NetAppNVMeDriver connector field translation."""

    def test_initialize_connection_translates_initiator_to_nqn(self):
        """Test that initiator field is copied to nqn field."""
        # Mock the parent __init__ to avoid needing real config
        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "__init__", return_value=None
        ):
            driver = netapp_nvme.NetAppNVMeDriver("driver", "nvme")

        volume = {"id": "test-volume"}
        connector = {"initiator": "nqn.2014-08.test:nvme:host01"}

        # Mock the parent initialize_connection
        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver,
            "initialize_connection",
            return_value={"driver_volume_type": "nvmeof"},
        ) as mock_parent:
            result = driver.initialize_connection(volume, connector)

            # Verify nqn was set from initiator
            assert connector["nqn"] == "nqn.2014-08.test:nvme:host01"

            # Verify parent was called
            mock_parent.assert_called_once_with(volume, connector)

            # Verify result was returned
            assert result == {"driver_volume_type": "nvmeof"}

    def test_initialize_connection_preserves_existing_nqn(self):
        """Test that existing nqn field is not overwritten."""
        # Mock the parent __init__ to avoid needing real config
        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "__init__", return_value=None
        ):
            driver = netapp_nvme.NetAppNVMeDriver("driver", "nvme")

        volume = {"id": "test-volume"}
        connector = {
            "initiator": "nqn.2014-08.old:nvme:host01",
            "nqn": "nqn.2014-08.new:nvme:host01",
        }

        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "initialize_connection", return_value={}
        ):
            driver.initialize_connection(volume, connector)

            # Verify existing nqn was preserved
            assert connector["nqn"] == "nqn.2014-08.new:nvme:host01"

    def test_initialize_connection_no_initiator_field(self):
        """Test handling when initiator field is missing."""
        # Mock the parent __init__ to avoid needing real config
        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "__init__", return_value=None
        ):
            driver = netapp_nvme.NetAppNVMeDriver("driver", "nvme")

        volume = {"id": "test-volume"}
        connector = {"nqn": "nqn.2014-08.test:nvme:host01"}

        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "initialize_connection", return_value={}
        ):
            driver.initialize_connection(volume, connector)

            # Verify nqn unchanged
            assert connector["nqn"] == "nqn.2014-08.test:nvme:host01"

    def test_terminate_connection_translates_initiator_to_nqn(self):
        """Test that initiator field is copied to nqn field on terminate."""
        # Mock the parent __init__ to avoid needing real config
        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "__init__", return_value=None
        ):
            driver = netapp_nvme.NetAppNVMeDriver("driver", "nvme")

        volume = {"id": "test-volume"}
        connector = {"initiator": "nqn.2014-08.test:nvme:host01"}

        # Mock the parent terminate_connection
        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "terminate_connection", return_value=None
        ) as mock_parent:
            driver.terminate_connection(volume, connector)

            # Verify nqn was set from initiator
            assert connector["nqn"] == "nqn.2014-08.test:nvme:host01"

            # Verify parent was called
            mock_parent.assert_called_once_with(volume, connector)

    def test_terminate_connection_handles_none_connector(self):
        """Test that None connector doesn't cause errors on terminate."""
        # Mock the parent __init__ to avoid needing real config
        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "__init__", return_value=None
        ):
            driver = netapp_nvme.NetAppNVMeDriver("driver", "nvme")

        volume = {"id": "test-volume"}

        # Mock the parent terminate_connection
        with mock.patch.object(
            netapp_nvme.NetAppCmodeNVMeDriver, "terminate_connection", return_value=None
        ) as mock_parent:
            driver.terminate_connection(volume, None)

            # Verify parent was called with None
            mock_parent.assert_called_once_with(volume, None)
