"""NetApp NVMe driver with dynamic multi-SVM support."""

from cinder import context
from cinder import exception
from cinder import interface
from cinder.volume import configuration
from cinder.volume import driver as volume_driver
from cinder.volume import volume_types
from cinder.volume import volume_utils
from cinder.volume.drivers.netapp import options
from cinder.volume.drivers.netapp import utils as na_utils
from cinder.volume.drivers.netapp.dataontap.client import client_cmode_rest
from cinder.volume.drivers.netapp.dataontap.nvme_library import NetAppNVMeStorageLibrary
from cinder.volume.drivers.netapp.dataontap.performance import perf_cmode
from cinder.volume.drivers.netapp.dataontap.utils import capabilities
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
    volume_driver.volume_opts,
    options.netapp_proxy_opts,
    options.netapp_connection_opts,
    options.netapp_transport_opts,
    options.netapp_basicauth_opts,
    options.netapp_provisioning_opts,
    options.netapp_cluster_opts,
    options.netapp_san_opts,
    options.netapp_support_opts,
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

    REQUIRED_CMODE_FLAGS = []

    def do_setup(self, ctxt, svm_name):
        """Override the upstream implementation to dynamically set the svm.

        This is a copy and paste of the driver except the get_client_for_backend()
        call is replaced with one that uses our custom config
        """
        na_utils.check_flags(self.REQUIRED_FLAGS, self.configuration)
        self.namespace_ostype = (
            self.configuration.netapp_namespace_ostype or self.DEFAULT_NAMESPACE_OS
        )
        self.host_type = self.configuration.netapp_host_type or self.DEFAULT_HOST_TYPE

        na_utils.check_flags(self.REQUIRED_CMODE_FLAGS, self.configuration)

        self.client = client_cmode_rest.RestClient(
            transport_type=self.configuration.netapp_transport_type,
            ssl_cert_path=self.configuration.netapp_ssl_cert_path,
            username=self.configuration.netapp_login,
            password=self.configuration.netapp_password,
            hostname=self.configuration.netapp_server_hostname,
            port=self.configuration.netapp_server_port,
            vserver=self.configuration.netapp_vserver,
            trace=volume_utils.TRACE_API,
            api_trace_pattern=self.configuration.netapp_api_trace_pattern,
            async_rest_timeout=self.configuration.netapp_async_rest_timeout,
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
        LOG.info("Initializing %s", self.DRIVER_NAME)
        super().__init__(*args, **kwargs)
        # this is where we'll keep each SVM scoped instance of the upstream NetApp lib
        self._libraries = {}
        # this is where we will keep the NetApp lib initialization params
        self._lib_init = kwargs
        # save the config
        self.configuration = kwargs["configuration"]
        for opts in NETAPP_DYNAMIC_OPTS:
            self.configuration.append_config_values(opts)
        # work around default used in drivers for the cfg override below
        # by dragging it from the SHARED_CONF_GROUP to our driver group
        CONF.set_override(
            "max_over_subscription_ratio",
            self.configuration.safe_get("max_over_subscription_ratio"),
            group=self.configuration.config_group,
        )
        # we want to provide a unique configuration to each lib init
        del self._lib_init["configuration"]
        # stats cache
        self._stats = {}
        LOG.info("initialized dynamic nvme")

    def _get_svms(self):
        prefix = self.configuration.safe_get("netapp_vserver_prefix") or "os-"
        svm_filter = {
            "state": "running",
            "nvme.enabled": "true",
            "name": f"{prefix}*",
            "fields": "name,uuid",
        }
        ret = self.cluster.get_records(
            "svm/svms", query=svm_filter, enable_tunneling=False
        )

        return [rec["name"] for rec in ret["records"]]

    def _add_svm_lib(self, svm_name, ctxt=None):
        LOG.info("Setting up SVM %s", svm_name)
        if ctxt is None:
            ctxt = context.get_admin_context()
        # dynamically generate a new config section
        new_cfg_grp = f"{self.configuration.config_group}-{svm_name}"
        cfg = configuration.BackendGroupConfiguration(
            volume_driver.volume_opts,
            config_group=new_cfg_grp,
        )
        # add the netapp_vserver option
        cfg.append_config_values(options.netapp_cluster_opts)
        # the shared values come from our main driver config
        cfg.shared_backend_conf = CONF._get(self.configuration.config_group)
        # set the vserver
        CONF.set_override("netapp_vserver", svm_name, group=new_cfg_grp)
        # set an unique volume_backend_name for the SSC and capabilities libraries
        CONF.set_override("volume_backend_name", new_cfg_grp, group=new_cfg_grp)
        # create a new instance
        lib = NetAppNVMeStorageLibrary(
            self.DRIVER_NAME, "NVMe", configuration=cfg, **self._lib_init
        )
        lib.do_setup(ctxt, svm_name)
        lib.check_for_setup_error()
        self._libraries[svm_name] = lib

    def _volume_to_library(self, volume):
        LOG.info("got called for volume %s", volume)
        volume_type = _get_volume_type(volume)
        _validate_volume_type(volume_type)
        prefix = self.configuration.safe_get("netapp_vserver_prefix") or "os-"
        svm_name = f"{prefix}-{volume_type.projects[0]}"
        # load an existing cached instance
        lib = self._libraries.get(svm_name)
        if lib is None:
            raise exception.DriverNotInitialized()
        return lib

    @staticmethod
    def get_driver_options():
        return NETAPP_DYNAMIC_OPTS

    def do_setup(self, ctxt):
        """Setup the driver.

        Connected to the NetApp with cluster credentials to find the SVMs.
        """
        self.cluster = client_cmode_rest.RestClient(
            transport_type=self.configuration.netapp_transport_type,
            ssl_cert_path=self.configuration.netapp_ssl_cert_path,
            username=self.configuration.netapp_login,
            password=self.configuration.netapp_password,
            hostname=self.configuration.netapp_server_hostname,
            port=self.configuration.netapp_server_port,
            vserver=None,
            trace=volume_utils.TRACE_API,
            api_trace_pattern=self.configuration.netapp_api_trace_pattern,
            async_rest_timeout=self.configuration.netapp_async_rest_timeout,
        )
        svms = self._get_svms()
        for svm_name in svms:
            self._add_svm_lib(svm_name, ctxt)

    def check_for_setup_error(self):
        """Check for setup errors."""
        for svm_name, _ in self._libraries.items():
            LOG.info("Calling do_setup for SVM %s", svm_name)

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
        # return self.library.create_snapshot(snapshot)

    def delete_snapshot(self, snapshot):
        """Delete a snapshot."""
        raise exception.DriverNotInitialized()
        # return self.library.delete_snapshot(snapshot)

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
            LOG.info("would refresh")
            data = {}
            data["volume_backend_name"] = (
                self.configuration.safe_get("volume_backend_name") or self.DRIVER_NAME
            )
            data["vendor_name"] = "NetApp"
            data["driver_version"] = self.VERSION
            data["storage_protocol"] = "NVMe"
            data["sparse_copy_volume"] = True
            data["replication_enabled"] = False
            data["pools"] = []
            self._stats = data
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
