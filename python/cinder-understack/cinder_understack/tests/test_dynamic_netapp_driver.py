"""Test NetApp dynamic driver implementation."""

from unittest import mock

from cinder.tests.unit import test
from cinder.tests.unit.volume.drivers.netapp import fakes as na_fakes
from cinder.volume.drivers.netapp.dataontap.nvme_library import NetAppNVMeStorageLibrary

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
        cfg = na_fakes.create_configuration()
        cfg.netapp_login = "fake_user"
        cfg.netapp_password = "fake_pass"  # noqa: S105
        cfg.netapp_server_hostname = "127.0.0.1"
        return cfg

    def _setup_rest_mock(self, rest):
        rest.get_ontap_version = mock.Mock(return_value=(9, 16, 0))

    def test_driver_has_correct_attributes(self):
        """Test that driver has expected attributes."""
        self.assertEqual("1.0.0", self.driver.VERSION)
        self.assertEqual("NetApp_Dynamic_NVMe", self.driver.DRIVER_NAME)

    def test_driver_has_library_instance(self):
        """Test that driver has library instance."""
        self.assertIsInstance(self.library, dynamic_netapp_driver.NetappDynamicLibrary)

    def test_library_inherits_from_netapp_library(self):
        """Test that library inherits from NetApp NVMe library."""
        self.assertIsInstance(self.library, NetAppNVMeStorageLibrary)

    @mock.patch("cinder_understack.dynamic_netapp_driver.RestNaServer")
    @mock.patch.object(NetAppNVMeStorageLibrary, "do_setup")
    @mock.patch.object(dynamic_netapp_driver.NetAppMinimalLibrary, "do_setup")
    def test_do_setup_calls_library(self, new_do_setup, old_do_setup, mock_rest):
        """Test that do_setup delegates to library."""
        self._setup_rest_mock(mock_rest)
        context = mock.Mock()
        self.driver.do_setup(context)
        # not yet wired in
        new_do_setup.assert_not_called()
        old_do_setup.assert_not_called()

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
