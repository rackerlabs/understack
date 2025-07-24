"""Metadata-based backend config."""

from cinder import exception
from cinder.volume import driver as volume_driver
from cinder.volume.drivers.netapp import options
# from cinder.volume.drivers.netapp.dataontap.block_cmode import (
#     NetAppBlockStorageCmodeLibrary,
# )
from cinder.volume.drivers.netapp.dataontap.nvme_library import NetAppNVMeStorageLibrary

from cinder.volume.drivers.netapp.dataontap.client.client_cmode_rest import (
    RestClient as RestNaServer,
)

from cinder.volume.drivers.netapp.dataontap.performance.perf_base import PerformanceLibrary
from cinder.volume.drivers.netapp.dataontap.utils.capabilities import CapabilitiesLibrary
from cinder import context
from cinder.objects import volume_type as vol_type_obj
from oslo_config import cfg
from oslo_log import log as logging
import remote_pdb

# Dev: from remote_pdb import remote_pdb

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

# Register necessary config options under a unique group name 'dynamic_netapp'
CONF.register_opts(options.netapp_connection_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_transport_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_basicauth_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_provisioning_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_cluster_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_san_opts, group="netapp_nvme")
CONF.register_opts(volume_driver.volume_opts, group="netapp_nvme")

# CONF.set_override("storage_protocol", "nvme", group="dynamic_netapp")
# CONF.set_override("netapp_storage_protocol", "nvme", group="dynamic_netapp")
# Upstream NetApp driver registers this option with choices=["iSCSI", "FC"]
# So "nvme" will raise a ValueError at boot. Instead, we handle this per-volume below.


class NetappCinderDynamicDriver(NetAppNVMeStorageLibrary):
    """Metadata-based backend config."""
    def __init__(self, *args, **kwargs):
        self.initialized = False
        self.client = None
        driver_name = kwargs.pop("driver_name", "NetAppDynamicNVMe")
        driver_protocol = kwargs.pop("driver_protocol", "nvme")
        self.app_version = kwargs.get("app_version", "1.0.0")
        super().__init__(driver_name, driver_protocol, **kwargs)
        self.ssc_library = None
        self.perf_library = None


    def get_volume_stats(self, refresh=False):
        remote_pdb.set_trace('0.0.0.0',5555)
        return super().get_volume_stats(refresh=refresh)

    @property
    def supported(self):
        # Used by Cinder to determine whether this driver is active/enabled
        return True

    def get_version(self):
        # Called at Cinder service startup to report backend driver version
        return "NetappCinderDynamicDriver 1.0"

    #   base class (NetAppNVMeStorageLibrary) uses do_setup() to:
    #   Check netapp_login, netapp_password, etc.
    #   Build a REST client from config at startup (via dot_utils.get_client_for_backend())
    #   But our model fetches those from volume.volume_type.extra_specs,
    #   which aren’t available until create_volume()
    def do_setup(self, context):
        LOG.info("Skipping static do_setup in dynamic NVMe driver.")
        self.namespace_ostype = self.DEFAULT_NAMESPACE_OS
        self.host_type = self.DEFAULT_HOST_TYPE
        self._stats = {}
        self.ssc_library = None
        self.perf_library = None
        # self.ssc_library = None

    def check_for_setup_error(self):
        LOG.info("Skipping static check_for_setup_error in dynamic driver.")


    def init_capabilities(self):
        # Required by Cinder schedulers — called from get_volume_stats()
        # If removed, scheduling filters based on capabilities may fail
        max_over_subscription_ratio = (self.configuration.max_over_subscription_ratio,)
        self._capabilities = {
            "thin_provisioning_support": True,
            "thick_provisioning_support": True,
            "multiattach": True,
            "snapshot_support": True,
            "max_over_subscription_ratio": max_over_subscription_ratio,
        }

    def set_initialized(self):
        # Called by Cinder VolumeManager at the end of init_host()
        # If not defined, VolumeManager may assume the driver is not ready
        self.initialized = True


    def _init_client_from_any_existing_volume_type(self):
        # remote_pdb.set_trace('0.0.0.0',5555)
        ctxt = context.get_admin_context()
        try:
            types = vol_type_obj.VolumeTypeList.get_all(ctxt)
            for vt in types:
                specs = vt.extra_specs
                if all(k in specs for k in ["netapp:svm_hostname", "netapp:svm_username", "netapp:svm_password", "netapp:svm_vserver"]):
                    LOG.info(f"Initializing REST client using volume type: {vt.name}")
                    return self._init_rest_client(
                        specs["netapp:svm_hostname"],
                        specs["netapp:svm_username"],
                        specs["netapp:svm_password"],
                        specs["netapp:svm_vserver"]
                    )
        except Exception as e:
            LOG.warning("Failed to init client from any volume type: %s", e)
        return None

    def get_volume_stats(self, refresh=False):

        remote_pdb.set_trace('0.0.0.0',5555)
        if not self.client:
            self.client = self._init_client_from_any_existing_volume_type()

        if not hasattr(self, "client") or self.client is None:
            LOG.warning("NetApp client not initialized. Returning fallback stats.")
            return {
                "volume_backend_name": "dynamic_backend",
                "vendor_name": "NetApp",
                "driver_version": self.VERSION,
                "storage_protocol": self.driver_protocol,
                "pools": [self._get_fallback_pool()],
            }

        if not self.ssc_library:
            try:
                self.ssc_library = CapabilitiesLibrary(
                    protocol='nvme',
                    vserver_name=self.client.vserver,
                    zapi_client=None,
                    configuration=self.configuration
                )
            except Exception as e:
                LOG.warning("Could not initialize SSC: %s", e)

        if not self.perf_library:
            try:
                self.perf_library = PerformanceLibrary(self.client)
            except Exception as e:
                LOG.warning("Could not initialize Perf lib: %s", e)

        self._update_volume_stats()
        return self._stats

    def _update_volume_stats(self):
        LOG.info("Fetching live volume stats from NetApp SVM")
        pools = self._get_ssc_pool_stats()
        self._stats = {
            "volume_backend_name": self.configuration.safe_get("volume_backend_name") or "dynamic_backend",
            "vendor_name": "NetApp",
            "driver_version": self.VERSION,
            "storage_protocol": self.driver_protocol,
            "pools": pools,
        }
    def _get_ssc_pool_stats(self):
        pools = []
        ssc = self.ssc_library.get_ssc()
        if not ssc:
            return pools

        if self.client.get_connection_type() == "cluster":
            self.perf_library.update_performance_cache(ssc)
            aggregates = self.ssc_library.get_ssc_aggregates()
            aggr_cap = self.client.get_aggregate_capacities(aggregates)
        else:
            aggr_cap = {}

        for vol_name, vol_info in ssc.items():
            pool = dict(vol_info)
            pool["pool_name"] = vol_name
            pool["QoS_support"] = False
            pool["multiattach"] = False
            pool["online_extend_support"] = False
            pool["consistencygroup_support"] = False
            pool["consistent_group_snapshot_enabled"] = False
            pool["reserved_percentage"] = 0
            pool["max_over_subscription_ratio"] = 20.0

            cap = self.client.get_flexvol_capacity(vol_name)
            pool["total_capacity_gb"] = cap["size-total"] // (1024**3)
            pool["free_capacity_gb"] = cap["size-available"] // (1024**3)

            if self.configuration.netapp_driver_reports_provisioned_capacity:
                namespaces = self.client.get_namespace_sizes_by_volume(vol_name)
                provisioned = sum(ns["size"] for ns in namespaces)
                pool["provisioned_capacity_gb"] = provisioned // (1024**3)

            aggr_name = vol_info.get("netapp_aggregate")
            pool["netapp_aggregate_used_percent"] = aggr_cap.get(aggr_name, {}).get("percent-used", 0)
            pool["netapp_dedupe_used_percent"] = self.client.get_flexvol_dedupe_used_percent(vol_name)
            pool["utilization"] = self.perf_library.get_node_utilization_for_pool(vol_name)

            pools.append(pool)
        return pools

    def _get_fallback_pool(self):
        return {
            "pool_name": "fallback_pool",
            "total_capacity_gb": 0,
            "free_capacity_gb": 0,
            "reserved_percentage": 0,
            "max_over_subscription_ratio": 20.0,
            "thin_provisioning_support": True,
            "thick_provisioning_support": False,
            "multiattach": False,
            "QoS_support": False,
            "compression_support": False,
        }
    def _get_dynamic_pool_stats(self):
        remote_pdb.set_trace('0.0.0.0',5555)
        if not hasattr(self, "client"):
            LOG.warning("NetApp client not initialized; returning default dummy pool.")
            return {
                "pool_name": "default_pool",
                "total_capacity_gb": 0,
                "free_capacity_gb": 0,
                "reserved_percentage": 0,
                "max_over_subscription_ratio": 20.0,
                "provisioned_capacity_gb": 0,
                "allocated_capacity_gb": 0,
                "thin_provisioning_support": True,
                "thick_provisioning_support": False,
                "multiattach": True,
                "QoS_support": False,
                "compression_support": False,
            }

        pool_list = []
        try:
            # remote_pdb(''0.0.0.0'', 5555).set_trace()
            flexvols = self.client.get_flexvols()
            LOG.debug("Discovered FlexVols: %s", [v['name'] for v in flexvols])
            for vol in flexvols:
                pool = {
                    "pool_name": vol["name"],
                    "total_capacity_gb": float(vol["size"]) / (1024**3),
                    "free_capacity_gb": float(vol["available"]) / (1024**3),
                    "reserved_percentage": 0,
                    "max_over_subscription_ratio": 20.0,
                    "provisioned_capacity_gb": float(vol["used"]) / (1024**3),
                    "allocated_capacity_gb": 0,
                    "thin_provisioning_support": True,
                    "thick_provisioning_support": False,
                    "multiattach": True,
                    "QoS_support": False,
                    "compression_support": False,
                }
                pool_list.append(pool)
        except Exception as e:
            LOG.exception("Failed to fetch FlexVols from NetApp: %s", e)
            # Return fallback dummy pool to avoid total failure
            pool_list.append({
                "pool_name": "fallback",
                "total_capacity_gb": 0,
                "free_capacity_gb": 0,
                "reserved_percentage": 0,
                "max_over_subscription_ratio": 20.0,
                "provisioned_capacity_gb": 0,
                "allocated_capacity_gb": 0,
                "thin_provisioning_support": True,
                "thick_provisioning_support": False,
                "multiattach": True,
                "QoS_support": False,
                "compression_support": False,
            })

        # For now, return first pool (or enhance get_volume_stats to return all)
        return pool_list[0] if pool_list else {}

    def get_filter_function(self):
        # Required for Cinder's scheduler. If not present, Cinder logs an AttributeError
        return self.configuration.safe_get("filter_function") or None

    def get_goodness_function(self):
        # Paired with get_filter_function for scoring
        return self.configuration.safe_get("goodness_function") or None


    def update_provider_info(self, *args, **kwargs):
        # Called during _sync_provider_info() in VolumeManager.
        # If not implemented, Cinder raises a TypeError during service startup.
        # Wrote this logic because it was registered with 3 and was called using 2 args
        # There is issue with in-built drivers calling logic
        if len(args) == 2:
            volumes, snapshots = args
        elif len(args) >= 3:
            _, volumes, snapshots = args[:3]
        else:
            raise TypeError(
                "update_provider_info() expects at least volumes and snapshots."
            )
        return {}, {}

    def set_throttle(self):
        # Got AttributeError
        pass

    def _init_rest_client(self, hostname, username, password, vserver):
        # Called from create_volume() to create per-SVM REST connection
        # This avoids use of global CONF and uses metadata-driven parameters
        #todo: Need to circel back here for certs
        return RestNaServer(
            hostname=hostname,
            username=username,
            password=password,
            vserver=vserver,
            transport_type="https",
            port=443,
            ssl_cert_path=None,
            private_key_file=None,
            certificate_file=None,
            ca_certificate_file=None,
            ca_cert_file=None,
            trace=False,
            api_trace_pattern="(.*)",
            certificate_host_validation=False
        )

    def clean_volume_file_locks(self, volume):
        # Got this when volume was created and mocked the NetApp connection.
        # When creation failed,
        # it started its cleanup process and errored out for this method.
        # In our case, REST-based NetApp doesn’t need this,
        # but must be present to avoid errors.
        LOG.debug("No-op clean_volume_file_locks in dynamic driver")

    def create_volume(self, volume):
        # Called directly by Cinder during volume create workflow (create_volume.py)
        # This is where we extract runtime metadata (hostname, creds, protocol, etc.)
        # from volume type extra_specs and establish REST client connection.
        remote_pdb.set_trace('0.0.0.0',5555)
        specs = volume.volume_type.extra_specs
        hostname = specs.get("netapp:svm_hostname")
        username = specs.get("netapp:svm_username")
        password = specs.get("netapp:svm_password")
        vserver = specs.get("netapp:svm_vserver")
        protocol = specs.get("netapp:svm_protocol", "nvme")

        if not all([hostname, username, password, vserver]):
            raise exception.VolumeBackendAPIException(data="Missing NetApp metadata")

        self.client = self._init_rest_client(hostname, username, password, vserver)  # noqa: F841
        return super().create_volume(volume)
