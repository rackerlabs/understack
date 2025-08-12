"""Test NetApp dynamic driver implementation."""

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

    def get_config_base(self):
        """Get base configuration for testing."""
        return na_fakes.create_configuration()

    def test_driver_has_correct_attributes(self):
        """Test that driver has expected attributes."""
        self.assertEqual("1.0.0", self.driver.VERSION)
        self.assertEqual("NetApp_Dynamic_NVMe", self.driver.DRIVER_NAME)
