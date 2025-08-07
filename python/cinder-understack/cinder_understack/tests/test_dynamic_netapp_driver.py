"""Test NetApp dynamic driver implementation."""

from unittest import mock

from cinder.tests.unit import test
from cinder.tests.unit.volume.drivers.netapp import fakes as na_fakes

from cinder_understack import dynamic_netapp_driver


class NetappDynamicDriverTestCase(test.TestCase):
    """Test case for NetappCinderDynamicDriver."""

    def setUp(self):
        """Set up test case."""
        super().setUp()

        kwargs = {
            "configuration": self.get_config_base(),
            "host": "openstack@netapp_dynamic",
        }
        self.driver = dynamic_netapp_driver.NetappCinderDynamicDriver(**kwargs)
        self.library = self.driver.library

    def get_config_base(self):
        """Get base configuration for testing."""
        return na_fakes.create_configuration()

    def test_driver_has_correct_attributes(self):
        """Test that driver has expected attributes."""
        self.assertEqual("1.0.0", self.driver.VERSION)
        self.assertEqual("NetApp_Dynamic_NVMe", self.driver.DRIVER_NAME)

    def test_driver_has_library_instance(self):
        """Test that driver has library instance."""
        self.assertIsInstance(self.library, dynamic_netapp_driver.NetappDynamicLibrary)

    def test_library_inherits_from_netapp_library(self):
        """Test that library inherits from NetApp NVMe library."""
        from cinder.volume.drivers.netapp.dataontap.nvme_library import (
            NetAppNVMeStorageLibrary,
        )

        self.assertIsInstance(self.library, NetAppNVMeStorageLibrary)

    @mock.patch.object(dynamic_netapp_driver.NetappDynamicLibrary, "do_setup")
    def test_do_setup_calls_library(self, mock_do_setup):
        """Test that do_setup delegates to library."""
        context = mock.Mock()
        self.driver.do_setup(context)
        mock_do_setup.assert_called_once_with(context)

    @mock.patch.object(dynamic_netapp_driver.NetappDynamicLibrary, "create_volume")
    def test_create_volume_calls_library(self, mock_create_volume):
        """Test that create_volume delegates to library."""
        volume = mock.Mock()
        self.driver.create_volume(volume)
        mock_create_volume.assert_called_once_with(volume)

    @mock.patch.object(dynamic_netapp_driver.NetappDynamicLibrary, "get_volume_stats")
    def test_get_volume_stats_calls_library(self, mock_get_volume_stats):
        """Test that get_volume_stats delegates to library."""
        self.driver.get_volume_stats(refresh=True)
        mock_get_volume_stats.assert_called_once_with(True)
