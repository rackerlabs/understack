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
from cinder.volume.drivers.netapp.dataontap.utils import loopingcalls

from cinder_understack import dynamic_netapp_driver


def _create_mock_svm_lib(svm_name: str):
    mock_lib = mock.create_autospec(
        dynamic_netapp_driver.NetAppMinimalLibrary, instance=True
    )
    mock_lib.vserver = svm_name
    mock_lib.loopingcalls = loopingcalls.LoopingCalls()
    return mock_lib


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

    # Mocked check_for_setup_errort to avoid below error .
    # NetAppDriverException: No pools are available for provisioning volumes.
    @mock.patch(
        "cinder_understack.dynamic_netapp_driver.loopingcall.FixedIntervalLoopingCall"
    )
    @mock.patch.object(NetAppNVMeStorageLibrary, "check_for_setup_error")
    def test_looping_call_starts_once(self, mock_check_setup, mock_looping_call_class):
        """Test that looping call starts correctly and only once."""
        # To avoid config errors mocking the SVM lib setup check
        mock_check_setup.return_value = None

        # Mock instance for FixedIntervalLoopingCall
        mock_looping_instance = mock.Mock()
        mock_looping_call_class.return_value = mock_looping_instance

        # Clear the looping call so that it can be start
        self.driver._looping_call = None

        # Trigger setup error check ( to start the loop)
        self.driver.check_for_setup_error()

        # Verify loop initialized and started
        mock_looping_call_class.assert_called_once_with(
            self.driver._refresh_svm_libraries
        )
        # Todo: Use constants for interval and initial_delay
        mock_looping_instance.start.assert_called_once_with(interval=300)

        # Test second call should not start loop again
        mock_looping_instance.reset_mock()
        self.driver.check_for_setup_error()
        mock_looping_instance.start.assert_not_called()

    @mock.patch.object(
        dynamic_netapp_driver.NetappCinderDynamicDriver, "_create_svm_lib"
    )
    @mock.patch.object(dynamic_netapp_driver.NetappCinderDynamicDriver, "_get_svms")
    def test_refresh_svm_libraries_adds_and_removes_svms(
        self, mock_get_svms, mock_create_svm_lib
    ):
        """Test _refresh_svm_libraries add new SVMs and removes stale ones."""
        # Existing SVMs (before refresh called)
        expected_svm = f"os-{self.project_id}"

        self.driver._libraries = {
            "os-old-svm": _create_mock_svm_lib("os-old-svm"),
            expected_svm: _create_mock_svm_lib(expected_svm),
        }

        self.driver._get_svms = mock_get_svms
        # Returned by _get_svms (after refresh)
        mock_get_svms.return_value = [expected_svm, "os-new-svm"]

        # make the created lib look like the real thing
        mock_lib_instance = _create_mock_svm_lib("os-new-svm")
        mock_create_svm_lib.return_value = mock_lib_instance

        # Trigger refresh
        self.driver._context = self.ctxt

        self.driver._actual_refresh_svm_libraries(self.ctxt)

        # Check stale SVM was removed
        self.assertNotIn("os-old-svm", self.driver._libraries)

        # Check SVM was retained
        self.assertIn(expected_svm, self.driver._libraries)

        # Check new SVM was added
        self.assertIn("os-new-svm", self.driver._libraries)

        # New SVM lib should've been created and setup
        mock_create_svm_lib.assert_called_once_with("os-new-svm")
        mock_lib_instance.do_setup.assert_called_once_with(self.ctxt)
        mock_lib_instance.check_for_setup_error.assert_called_once()

    @mock.patch.object(
        dynamic_netapp_driver.NetappCinderDynamicDriver, "_create_svm_lib"
    )
    @mock.patch.object(dynamic_netapp_driver.NetappCinderDynamicDriver, "_get_svms")
    def test_refresh_svm_libraries_handles_lib_creation_failure(
        self, mock_get_svms, mock_create_svm_lib
    ):
        """Ensure that failure in lib creation is caught and logged, not raised."""
        test_svm_name = "os-new-failing_svm"
        mock_get_svms.return_value = [test_svm_name]
        mock_svm_lib = _create_mock_svm_lib(test_svm_name)
        mock_svm_lib.check_for_setup_error.side_effect = Exception("Simulated failure")
        mock_create_svm_lib.return_value = mock_svm_lib

        self.driver._libraries = {}

        # Should not raise exception
        self.driver._actual_refresh_svm_libraries(mock.Mock())

        # The failing SVM should not be added to self._libraries
        self.assertNotIn("os-new-failing-svm", self.driver._libraries)
