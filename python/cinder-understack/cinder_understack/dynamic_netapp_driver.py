"""NetApp NVMe driver with dynamic multi-SVM support."""

from collections.abc import Generator
from contextlib import contextmanager
from functools import cached_property

from cinder import context
from cinder import exception
from cinder import interface
from cinder.volume import configuration
from cinder.volume import driver as volume_driver
from cinder.volume import volume_utils
from cinder.volume.drivers.netapp import options as na_opts
from cinder.volume.drivers.netapp import utils as na_utils
from cinder.volume.drivers.netapp.dataontap.client.client_cmode_rest import (
    RestClient as RestNaServer,
)
from cinder.volume.drivers.netapp.dataontap.nvme_library import NetAppNVMeStorageLibrary
from cinder.volume.drivers.netapp.dataontap.performance import perf_cmode
from cinder.volume.drivers.netapp.dataontap.utils import capabilities
from oslo_config import cfg
from oslo_log import log as logging
from oslo_service import loopingcall

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

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
    cfg.IntOpt(
        "netapp_svm_discovery_interval",
        default=300,
        help="In seconds for SVM discovery. The driver will "
        "periodically scan the NetApp cluster for new SVMs matching the "
        "configured prefix.",
    ),
]

# Configuration options for dynamic NetApp driver
# Using cinder.volume.configuration approach for better abstraction
NETAPP_DYNAMIC_OPTS = [
    na_opts.netapp_connection_opts,
    na_opts.netapp_basicauth_opts,
    na_opts.netapp_transport_opts,
    na_opts.netapp_provisioning_opts,
    na_opts.netapp_support_opts,
    na_opts.netapp_san_opts,
    na_opts.netapp_cluster_opts,
    netapp_dynamic_opts,
]


# We use a + because of the special meaning of # in
# cinder/volume/volume_utils.py extract_host()
_SVM_NAME_DELIM = "+"


class NetAppMinimalLibrary(NetAppNVMeStorageLibrary):
    """Minimal overriding library.

    The purpose of this class is to take the existing upstream class
    and patch it as necessary to allow for our multi-SVM approach.
    This class is still intended to exist per SVM, its just fixes
    for that approach.
    """

    def __init__(self, driver_name, driver_protocol, **kwargs):
        super().__init__(driver_name, driver_protocol, **kwargs)
        # the upstream library sets this field by parsing the host
        # which is "pod@config_group" in syntax. The issue is that
        # will point to our parent group. This backend_name is then
        # used by the connection code which reloads the whole configuration
        # but now it loaded the parent configuration and not the one targeting
        # the SVM. By fixing this backend_name it should point to the
        # right place.
        self.backend_name = self.configuration.config_group

    def do_setup(self, ctxt):
        """Override the upstream call.

        This is a copy and paste except for the self.client setup,
        instead of calling the library function which makes a brand new
        self.configuration object and then reads from that. This creates
        the rest client from our existing self.configuration so that we
        can supply our overridden one. If we had used the upstream one it
        would check that the dynamic config group we made existed in the
        parsed config, which it does not and it would then fail.
        """
        na_utils.check_flags(self.REQUIRED_FLAGS_BASIC, self.configuration)
        self.namespace_ostype = (
            self.configuration.netapp_namespace_ostype or self.DEFAULT_NAMESPACE_OS
        )
        self.host_type = self.configuration.netapp_host_type or self.DEFAULT_HOST_TYPE

        na_utils.check_flags(self.REQUIRED_CMODE_FLAGS, self.configuration)

        # this is the change from upstream right here
        self.client = RestNaServer(
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
            private_key_file=None,
            certificate_file=None,
            ca_certificate_file=None,
            certificate_host_validation=None,
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
        self.configuration.append_config_values(self.__class__.get_driver_options())
        # save the arguments supplied
        self._init_kwargs = kwargs
        # but we don't need the configuration
        del self._init_kwargs["configuration"]
        # child libraries
        self._libraries = {}
        # aggregated stats
        self._stats = self._empty_volume_stats()
        # looping call placeholder
        self._looping_call = None

    def _create_svm_lib(self, svm_name: str) -> NetAppMinimalLibrary:
        # we create a configuration object per SVM library to
        # provide the SVM name to the SVM library
        child_grp = f"{self.configuration.config_group}_{svm_name}"
        child_cfg = configuration.Configuration(
            volume_driver.volume_opts,
            config_group=child_grp,
        )
        # register the options
        child_cfg.append_config_values(self.__class__.get_driver_options())
        # we need to copy the configs so get the base group
        for opt in self.__class__.get_driver_options():
            try:
                val = getattr(self.configuration, opt.name)
                CONF.set_override(opt.name, val, group=child_grp)
            except cfg.NoSuchOptError:
                # this exception occurs if the option isn't set at all
                # which means we don't need to set an override
                pass

        # now set the SVM name
        CONF.set_override("netapp_vserver", svm_name, group=child_grp)
        # now set the backend configuration name
        CONF.set_override("volume_backend_name", child_grp, group=child_grp)
        # return an instance of the library scoped to one SVM
        # netapp_mode=proxy is necessary to quiet the driver from reporting that
        # its not
        return NetAppMinimalLibrary(
            self.DRIVER_NAME,
            "NVMe",
            configuration=child_cfg,
            netapp_mode="proxy",
            **self._init_kwargs,
        )

    @staticmethod
    def get_driver_options():
        """All options this driver supports."""
        return [item for sublist in NETAPP_DYNAMIC_OPTS for item in sublist]

    @cached_property
    def cluster(self) -> RestNaServer:
        return RestNaServer(
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
            private_key_file=None,
            certificate_file=None,
            ca_certificate_file=None,
            certificate_host_validation=None,
        )

    def _get_svms(self):
        prefix = self.configuration.safe_get("netapp_vserver_prefix")
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

    def do_setup(self, ctxt):
        """Setup the driver.

        Connected to the NetApp with cluster credentials to find the SVMs.
        """
        for svm_name in self._get_svms():
            if svm_name in self._libraries:
                LOG.info("SVMe library already exists for SVM %s, skipping", svm_name)
                continue

            LOG.info("Creating NVMe library instance for SVM %s", svm_name)
            svm_lib = self._create_svm_lib(svm_name)
            svm_lib.do_setup(ctxt)
            self._libraries[svm_name] = svm_lib

    def _remove_svm_lib(self, svm_lib: NetAppMinimalLibrary):
        """Remove resources for a given SVM library."""
        # TODO: Need to free up resources here.
        for task in svm_lib.loopingcalls.tasks:
            task.looping_call.stop()
        svm_lib.loopingcalls.tasks = []

    def _refresh_svm_libraries(self):
        return self._actual_refresh_svm_libraries(context.get_admin_context())

    def _actual_refresh_svm_libraries(self, ctxt):
        """Refresh the SVM libraries."""
        LOG.info("Start refreshing SVM libraries")
        # Print all current library keys
        existing_libs = set(self._libraries.keys())
        LOG.info("Existing library keys: %s", existing_libs)
        # Get the current SVMs from cluster
        current_svms = set(self._get_svms())
        LOG.info("Current SVMs detected from cluster: %s", current_svms)
        # Remove libraries for SVMs that no longer exist
        stale_svms = existing_libs - current_svms
        for svm_name in stale_svms:
            LOG.info("Removing stale NVMe library for SVM: %s", svm_name)
            svm_lib = self._libraries[svm_name]
            self._remove_svm_lib(svm_lib)
            del self._libraries[svm_name]

        # Add new SVM libraries
        new_svms = current_svms - existing_libs
        for svm_name in new_svms:
            LOG.info("Creating NVMe library for new SVM: %s", svm_name)
            lib = self._create_svm_lib(svm_name)
            try:
                # Call do_setup to initialize the library
                lib.do_setup(ctxt)
                lib.check_for_setup_error()
                LOG.info("Library creation success for SVM: %s", svm_name)
                self._libraries[svm_name] = lib
            except Exception:
                LOG.exception(
                    "Failed to create library for SVM %s",
                    svm_name,
                )
                self._remove_svm_lib(lib)
        LOG.info("Final libraries loaded: %s", list(self._libraries.keys()))

    def check_for_setup_error(self):
        """Check for setup errors."""
        svm_to_init = set(self._libraries.keys())
        for svm_name in svm_to_init:
            LOG.info("Checking NVMe library for errors for SVM %s", svm_name)
            svm_lib = self._libraries[svm_name]
            try:
                svm_lib.check_for_setup_error()
            except Exception:
                LOG.exception("Failed to initialize SVM %s, skipping", svm_name)
                self._remove_svm_lib(svm_lib)
                del self._libraries[svm_name]

        # looping call to refresh SVM libraries
        if not self._looping_call:
            interval = self.configuration.safe_get("netapp_svm_discovery_interval")
            if interval and interval > 0:
                self._looping_call = loopingcall.FixedIntervalLoopingCall(
                    self._refresh_svm_libraries
                )
                # removed initial_delay the first call run after full interval .
                self._looping_call.start(interval=interval)
            else:
                LOG.info("SVM discovery timer disabled (interval=%s)", interval)

    def _svmify_pool(self, pool: dict, svm_name: str, **kwargs) -> dict:
        """Applies SVM info to a pool so we can target it and track it."""
        # We need to prefix our pool_name, which is 1:1 with the FlexVol
        # name on the SVM, with the SVM name. This is because the name of
        # a FlexVol is unique within 1 SVM. Two different SVMs can have
        # the same FlexVol however so we need to prefix it. We avoid
        # using # as our separator because it has special meaning to
        # cinder. See the cinder/volume/volume_utils.py extract_host()
        # function for details.
        pool_name = pool["pool_name"]
        pool["pool_name"] = f"{svm_name}{_SVM_NAME_DELIM}{pool_name}"
        pool["netapp_vserver"] = svm_name
        prefix = self.configuration.safe_get("netapp_vserver_prefix")
        pool["netapp_project_id"] = svm_name.replace(prefix, "")
        pool.update(kwargs)
        return pool

    @contextmanager
    def _volume_to_library(self, volume) -> Generator[NetAppMinimalLibrary]:
        """From a volume find the specific NVMe library to use."""
        # save this to restore it in the end
        original_host = volume["host"]
        # svm plus pool_name
        svm_pool_name = volume_utils.extract_host(original_host, level="pool")
        if not svm_pool_name:
            raise exception.InvalidInput(
                reason=f"pool name not found in {original_host}"
            )

        svm_name = svm_pool_name.split(_SVM_NAME_DELIM)[0]
        # workaround when the svm_name has already been stripped from the pool
        prefix = self.configuration.netapp_vserver_prefix
        if not svm_name.startswith(prefix):
            LOG.debug(
                "Volume host already had SVM name stripped %s, "
                "using volume project_id %s",
                original_host,
                volume["project_id"],
            )
            svm_name = f"os-{volume['project_id']}"

        try:
            lib = self._libraries[svm_name]
        except KeyError:
            LOG.error("No such SVM %s instantiated", svm_name)
            raise exception.DriverNotInitialized() from None

        if lib.vserver != svm_name:
            LOG.error(
                "NVMe library vserver %s mismatch with volume.host SVM %s",
                lib.vserver,
                svm_name,
            )
            raise exception.InvalidInput(
                reason="NVMe library vserver mismatch with volume.host"
            )

        volume["host"] = original_host.replace(f"{svm_name}{_SVM_NAME_DELIM}", "")
        yield lib
        volume["host"] = original_host

    def create_volume(self, volume):
        """Create a volume."""
        with self._volume_to_library(volume) as lib:
            return lib.create_volume(volume)

    def delete_volume(self, volume):
        """Delete a volume."""
        with self._volume_to_library(volume) as lib:
            return lib.delete_volume(volume)

    def create_snapshot(self, snapshot):
        """Create a snapshot."""
        with self._volume_to_library(snapshot.volume) as lib:
            return lib.create_snapshot(snapshot)

    def delete_snapshot(self, snapshot):
        """Delete a snapshot."""
        with self._volume_to_library(snapshot.volume) as lib:
            return lib.delete_snapshot(snapshot)

    def create_volume_from_snapshot(self, volume, snapshot):
        """Create a volume from a snapshot."""
        with self._volume_to_library(volume) as lib:
            return lib.create_volume_from_snapshot(volume, snapshot)

    def create_cloned_volume(self, volume, src_vref):
        """Create a cloned volume."""
        with self._volume_to_library(volume) as lib:
            return lib.create_cloned_volume(volume, src_vref)

    def extend_volume(self, volume, new_size):
        """Extend a volume."""
        with self._volume_to_library(volume) as lib:
            return lib.extend_volume(volume, new_size)

    def initialize_connection(self, volume, connector):
        """Initialize connection to volume."""
        # TODO: the nova ironic driver sends the field 'initiator' but the NetApp
        # cinder driver expects the field to be 'nqn' so copy the field over
        if "initiator" in connector and "nqn" not in connector:
            connector["nqn"] = connector["initiator"]
        with self._volume_to_library(volume) as lib:
            return lib.initialize_connection(volume, connector)

    def terminate_connection(self, volume, connector, **kwargs):
        """Terminate connection to volume."""
        with self._volume_to_library(volume) as lib:
            return lib.terminate_connection(volume, connector, **kwargs)

    def get_filter_function(self):
        """Prefixes any filter function with our SVM matching."""
        base_filter = super().get_filter_function()
        svm_filter = "(capabilities.netapp_project_id == volume.project_id)"
        if base_filter:
            return f"{svm_filter} and {base_filter}"
        else:
            return svm_filter

    def _empty_volume_stats(self):
        data = {}
        data["volume_backend_name"] = (
            self.configuration.safe_get("volume_backend_name") or self.DRIVER_NAME
        )
        data["vendor_name"] = "NetApp"
        data["driver_version"] = self.VERSION
        data["storage_protocol"] = "NVMe"
        data["sparse_copy_volume"] = True
        data["replication_enabled"] = False
        # each SVM is going to have different limits
        data["total_capacity_gb"] = "unknown"
        data["free_capacity_gb"] = "unknown"
        # ensure we filter our pools by SVM
        data["filter_function"] = self.get_filter_function()
        data["goodness_function"] = self.get_goodness_function()
        data["pools"] = []
        return data

    def get_volume_stats(self, refresh=False):
        """Get volume stats."""
        if refresh:
            data = self._empty_volume_stats()
            for svm_name, svm_lib in self._libraries.items():
                LOG.info("Get Volume Stats for SVM %s", svm_name)
                ret = svm_lib.get_volume_stats(refresh)
                LOG.info("Adding SVM data to pools for SVM %s", svm_name)
                data["pools"].extend(
                    [
                        self._svmify_pool(
                            pool, svm_name, filter_function=data["filter_function"]
                        )
                        for pool in ret["pools"]
                    ]
                )
            self._stats = data
        return self._stats

    def create_export(self, context, volume, connector):
        """Create export for volume."""
        with self._volume_to_library(volume) as lib:
            return lib.create_export(context, volume)

    def ensure_export(self, context, volume):
        """Ensure export for volume."""
        with self._volume_to_library(volume) as lib:
            return lib.ensure_export(context, volume)

    def remove_export(self, context, volume):
        """Remove export for volume."""
        with self._volume_to_library(volume) as lib:
            return lib.remove_export(context, volume)
