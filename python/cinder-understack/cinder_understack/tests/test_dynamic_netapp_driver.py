"""Test NetApp dynamic driver implementation."""

import uuid
from unittest import mock

from cinder import context
from cinder import db
from cinder.tests.unit import fake_volume
from cinder.tests.unit import test
from cinder.tests.unit import utils as test_utils
from cinder.tests.unit.volume.drivers.netapp import fakes as na_fakes
from cinder.volume.drivers.netapp.dataontap.nvme_library import NetAppNVMeStorageLibrary

from cinder_understack import dynamic_netapp_driver


class NetappDynamicDriverTestCase(test.TestCase):
    """Test case for NetappCinderDynamicDriver."""

    def setUp(self):
        """Set up test case."""
        super().setUp()

        self.user_id = str(uuid.uuid4())
        self.project_id = str(uuid.uuid4())
        self.svms = [f"os-{self.project_id}"]

        self.ctxt = context.RequestContext(
            self.user_id, self.project_id, auth_token=True
        )

        kwargs = {
            "configuration": self.get_config_base(),
            "host": "openstack@netapp_dynamic",
        }
        self.driver = dynamic_netapp_driver.NetappCinderDynamicDriver(**kwargs)
        self.driver._cluster = mock.Mock()
        self.driver._get_svms = mock.Mock(return_value=self.svms)

        with mock.patch(
            "cinder_understack.dynamic_netapp_driver.RestNaServer"
        ) as mock_rest:
            self._setup_rest_mock(mock_rest)
            self.driver.do_setup(context.get_admin_context())
            for svm_name in self.svms:
                self.driver._libraries[svm_name].vserver = svm_name

    def get_config_base(self):
        """Get base configuration for testing."""
        cfg = na_fakes.create_configuration()
        cfg.netapp_login = "fake_user"
        cfg.netapp_password = "fake_pass"  # noqa: S105
        cfg.netapp_server_hostname = "127.0.0.1"
        return cfg

    def _setup_rest_mock(self, rest):
        rest.get_ontap_version = mock.Mock(return_value=(9, 16, 0))
        return rest

    def _get_fake_volume(self, vol_type_id):
        return fake_volume.fake_volume_obj(
            self.ctxt,
            name=na_fakes.VOLUME_NAME,
            size=4,
            id=na_fakes.VOLUME_ID,
            host=f"fake_host@fake_backend#os-{self.project_id}+fake_pool",
            volume_type_id=vol_type_id,
        )

    def test_driver_has_correct_attributes(self):
        """Test that driver has expected attributes."""
        self.assertEqual("1.0.0", self.driver.VERSION)
        self.assertEqual("NetApp_Dynamic_NVMe", self.driver.DRIVER_NAME)

    def test_library_inherits_from_netapp_library(self):
        """Test that library inherits from NetApp NVMe library."""
        for svm_lib in self.driver._libraries.values():
            self.assertIsInstance(svm_lib, NetAppNVMeStorageLibrary)

    @mock.patch.object(NetAppNVMeStorageLibrary, "do_setup")
    def test_do_setup_calls_library(self, old_do_setup):
        """Test that do_setup delegates to library."""
        self.driver.do_setup(self.ctxt)
        old_do_setup.assert_not_called()
        self.assertEqual(self.svms, list(self.driver._libraries.keys()))

    @mock.patch.object(NetAppNVMeStorageLibrary, "create_volume")
    def test_create_volume_calls_library(self, mock_create_volume):
        """Test that create_volume delegates to library."""
        ctxt = context.get_admin_context()
        self.driver.do_setup(ctxt)
        vol_type = test_utils.create_volume_type(
            ctxt,
            self,
            id=na_fakes.VOLUME.volume_type_id,
            name="my_vol_type",
            is_public=False,
        )
        db.volume_type_access_add(ctxt, vol_type.id, self.project_id)
        test_vol = self._get_fake_volume(vol_type.id)
        self.driver.create_volume(test_vol)
        mock_create_volume.assert_called_once_with(test_vol)

    @mock.patch.object(NetAppNVMeStorageLibrary, "get_volume_stats")
    def test_get_volume_stats_calls_library(self, mock_get_volume_stats):
        """Test that get_volume_stats delegates to library."""
        self.driver.get_volume_stats(refresh=True)
        mock_get_volume_stats.assert_called_with(True)
