"""Tests for NetApp NVMe connector translation."""

from unittest import mock

from cinder_understack import netapp_nvme


class TestNetAppNVMeLibrary:
    """Tests for NetAppNVMeLibrary connector field translation."""

    def test_initialize_connection_translates_initiator_to_nqn(self):
        """Test that initiator field is copied to nqn field."""
        # Mock the parent __init__ to avoid needing real config
        with mock.patch.object(
            netapp_nvme.NetAppNVMeStorageLibrary, "__init__", return_value=None
        ):
            lib = netapp_nvme.NetAppNVMeLibrary("driver", "nvme")

        volume = {"id": "test-volume"}
        connector = {"initiator": "nqn.2014-08.test:nvme:host01"}

        # Mock the parent initialize_connection
        with mock.patch.object(
            netapp_nvme.NetAppNVMeStorageLibrary,
            "initialize_connection",
            return_value={"driver_volume_type": "nvmeof"},
        ) as mock_parent:
            result = lib.initialize_connection(volume, connector)

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
            netapp_nvme.NetAppNVMeStorageLibrary, "__init__", return_value=None
        ):
            lib = netapp_nvme.NetAppNVMeLibrary("driver", "nvme")

        volume = {"id": "test-volume"}
        connector = {
            "initiator": "nqn.2014-08.old:nvme:host01",
            "nqn": "nqn.2014-08.new:nvme:host01",
        }

        with mock.patch.object(
            netapp_nvme.NetAppNVMeStorageLibrary,
            "initialize_connection",
            return_value={},
        ):
            lib.initialize_connection(volume, connector)

            # Verify existing nqn was preserved
            assert connector["nqn"] == "nqn.2014-08.new:nvme:host01"

    def test_initialize_connection_no_initiator_field(self):
        """Test handling when initiator field is missing."""
        # Mock the parent __init__ to avoid needing real config
        with mock.patch.object(
            netapp_nvme.NetAppNVMeStorageLibrary, "__init__", return_value=None
        ):
            lib = netapp_nvme.NetAppNVMeLibrary("driver", "nvme")

        volume = {"id": "test-volume"}
        connector = {"nqn": "nqn.2014-08.test:nvme:host01"}

        with mock.patch.object(
            netapp_nvme.NetAppNVMeStorageLibrary,
            "initialize_connection",
            return_value={},
        ):
            lib.initialize_connection(volume, connector)

            # Verify nqn unchanged
            assert connector["nqn"] == "nqn.2014-08.test:nvme:host01"
