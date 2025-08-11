"""NetApp NVMe driver with dynamic multi-SVM support."""

from cinder import context
from cinder import exception
from cinder import interface
from cinder.volume import driver as volume_driver
from cinder.volume import volume_types
from cinder.volume.drivers.netapp import options
from cinder.volume.drivers.netapp import utils as na_utils
from cinder.volume.drivers.netapp.dataontap.nvme_library import NetAppNVMeStorageLibrary
from cinder.volume.drivers.netapp.dataontap.performance import perf_cmode
from cinder.volume.drivers.netapp.dataontap.utils import capabilities
from cinder.volume.drivers.netapp.dataontap.utils import utils as dot_utils
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

# Configuration options for dynamic NetApp driver
# Following upstream patterns from cinder/volume/drivers/netapp/options.py

# Dynamic SVM options - our custom configuration group
netapp_dynamic_opts = [
    cfg.StrOpt(
        "netapp_vserver_prefix",
        default="os-",
        help="Prefix to use when constructing SVM/vserver names from tenant IDs. "
        "The SVM name will be formed as <prefix><tenant_id>. This allows "
        "the driver to dynamically select different SVMs based on the "
        "volume's project/tenant ID instead of being confined to one SVM.",
    ),
]

# All configuration option groups used by the dynamic driver
NETAPP_DYNAMIC_OPTS = [
    options.netapp_proxy_opts,
    options.netapp_connection_opts,
    options.netapp_transport_opts,
    options.netapp_basicauth_opts,
    options.netapp_provisioning_opts,
    options.netapp_cluster_opts,
    options.netapp_san_opts,
    volume_driver.volume_opts,
    netapp_dynamic_opts,
]


def _get_volume_type(volume):
    """Load the volume type from the volume."""
    if volume.volume_type:
        return volume.volume_type
    else:
        return volume_types.get_volume_type(None, volume.volume_type_id)


def _validate_volume_type(volume_type):
    if volume_type.is_public is not False:
        raise exception.InvalidVolumeType(
            reason="public volume types are not supported"
        )
    if not volume_type.projects:
        raise exception.InvalidVolumeType(
            reason="volume type must be assigned to a project"
        )
    if len(volume_type.projects) != 1:
        raise exception.InvalidVolumeType(
            reason="volume type must be assigned to ONE project"
        )


class NetappDynamicLibrary(NetAppNVMeStorageLibrary):
    """Add multi-SVM support to the upstream NetApp library."""

    # we are dynamically supplying the svm name so don't require the param
    REQUIRED_CMODE_FLAGS = []

    def do_setup(self, ctxt, svm_name):
        """Override the upstream implementation to dynamically set the svm.

        This is a copy and paste of the driver except the get_client_for_backend()
        call passing the svm instead of reading it from the config.
        """
        na_utils.check_flags(self.REQUIRED_FLAGS, self.configuration)
        self.namespace_ostype = (
            self.configuration.netapp_namespace_ostype or self.DEFAULT_NAMESPACE_OS
        )
        self.host_type = self.configuration.netapp_host_type or self.DEFAULT_HOST_TYPE

        na_utils.check_flags(self.REQUIRED_CMODE_FLAGS, self.configuration)

        # NOTE(felipe_rodrigues): NVMe driver is only available with
        # REST client.
        self.client = dot_utils.get_client_for_backend(
            self.backend_name, vserver_name=svm_name, force_rest=True
        )
        self.vserver = self.client.vserver

        # Storage service catalog.
        self.ssc_library = capabilities.CapabilitiesLibrary(
            self.driver_protocol, self.vserver, self.client, self.configuration
        )

        self.ssc_library.check_api_permissions()

        self.using_cluster_credentials = self.ssc_library.cluster_user_supported()

        # Performance monitoring library.
        self.perf_library = perf_cmode.PerformanceCmodeLibrary(self.client)


@interface.volumedriver
class NetappCinderDynamicDriver(volume_driver.BaseVD):
    """NetApp NVMe driver with dynamic multi-SVM support.

    This driver follows the standard Cinder pattern by inheriting from BaseVD
    and delegating storage operations to the NetappDynamicLibrary.
    """

    VERSION = "1.0.0"
    DRIVER_NAME = "NetApp_Dynamic_NVMe"

    def __init__(self, *args, **kwargs):
        """Initialize the driver and create library instance."""
        super().__init__(*args, **kwargs)
        # this is where we'll keep each SVM scoped instance of the upstream NetApp lib
        self._libraries = {}
        # this is where we will keep the NetApp lib initialization params
        self._lib_init = kwargs
        # save the config
        self.configuration = kwargs["configuration"]
        for opts in NETAPP_DYNAMIC_OPTS:
            self.configuration.append_config_values(opts)
        # stats cache
        self._stats = {}

    def _volume_to_library(self, volume):
        LOG.info("got called for volume %s", volume)
        volume_type = _get_volume_type(volume)
        _validate_volume_type(volume_type)
        prefix = self.configuration.safe_get("netapp_vserver_prefix") or "os-"
        svm_name = f"{prefix}-{volume_type.projects[0]}"
        # load an existing cached instance
        lib = self._libraries.get(svm_name)
        if lib is None:
            ctxt = context.get_admin_context()
            # create a new instance if needed
            lib = NetappDynamicLibrary(self.DRIVER_NAME, "NVMe", **self._lib_init)
            lib.do_setup(ctxt, svm_name)
            lib.check_for_setup_error()
            self._libraries[svm_name] = lib

        return lib

    @staticmethod
    def get_driver_options():
        return NETAPP_DYNAMIC_OPTS

    def do_setup(self, ctxt):
        """Setup the driver."""
        for svm_name, lib in self._libraries.items():
            LOG.info("Calling do_setup for SVM %s", svm_name)
            lib.do_setup(ctxt, svm_name)

    def check_for_setup_error(self):
        """Check for setup errors."""
        for svm_name, lib in self._libraries.items():
            LOG.info("Calling do_setup for SVM %s", svm_name)
            lib.check_for_setup_error()

    def create_volume(self, volume):
        """Create a volume."""
        lib = self._volume_to_library(volume)
        return lib.create_volume(volume)

    def delete_volume(self, volume):
        """Delete a volume."""
        lib = self._volume_to_library(volume)
        return lib.delete_volume(volume)

    def create_snapshot(self, snapshot):
        """Create a snapshot."""
        raise exception.DriverNotInitialized()
        return self.library.create_snapshot(snapshot)

    def delete_snapshot(self, snapshot):
        """Delete a snapshot."""
        raise exception.DriverNotInitialized()
        return self.library.delete_snapshot(snapshot)

    def create_volume_from_snapshot(self, volume, snapshot):
        """Create a volume from a snapshot."""
        lib = self._volume_to_library(volume)
        return lib.create_volume_from_snapshot(volume, snapshot)

    def create_cloned_volume(self, volume, src_vref):
        """Create a cloned volume."""
        lib = self._volume_to_library(volume)
        return lib.create_cloned_volume(volume, src_vref)

    def extend_volume(self, volume, new_size):
        """Extend a volume."""
        lib = self._volume_to_library(volume)
        return lib.extend_volume(volume, new_size)

    def initialize_connection(self, volume, connector):
        """Initialize connection to volume."""
        lib = self._volume_to_library(volume)
        return lib.initialize_connection(volume, connector)

    def terminate_connection(self, volume, connector, **kwargs):
        """Terminate connection to volume."""
        lib = self._volume_to_library(volume)
        return lib.terminate_connection(volume, connector, **kwargs)

    def get_volume_stats(self, refresh=False):
        """Get volume stats."""
        if refresh:
            LOG.INFO("would refresh")
        return self._stats

    def create_export(self, ctxt, volume, connector):
        """Create export for volume."""
        lib = self._volume_to_library(volume)
        return lib.create_export(ctxt, volume, connector)

    def ensure_export(self, ctxt, volume):
        """Ensure export for volume."""
        lib = self._volume_to_library(volume)
        return lib.ensure_export(ctxt, volume)

    def remove_export(self, ctxt, volume):
        """Remove export for volume."""
        lib = self._volume_to_library(volume)
        return lib.remove_export(ctxt, volume)
