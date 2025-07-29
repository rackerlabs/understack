"""Metadata-based backend config."""

from cinder import exception
from cinder.volume import driver as volume_driver
from cinder.volume.drivers.netapp import options
from cinder.volume.drivers.netapp.dataontap.block_cmode import (
    NetAppBlockStorageCmodeLibrary,
)
from cinder.volume.drivers.netapp.dataontap.client import api as netapp_api
from cinder.volume.drivers.netapp.dataontap.client.client_cmode_rest import (
    RestClient as RestNaServer,
)
from oslo_config import cfg
from oslo_log import log as logging

# Dev: from remote_pdb import RemotePdb

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

# We had to register netapp_proxy_opts because the original error was:
# "NoSuchOptError: no such option netapp_storage_protocol in group [netapp_nvme]"
# The standard NetApp drivers register this, but we missed it initially.
# Also switched from "dynamic_netapp" to "netapp_nvme" to match our backend name.
CONF.register_opts(options.netapp_proxy_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_connection_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_transport_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_basicauth_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_provisioning_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_cluster_opts, group="netapp_nvme")
CONF.register_opts(options.netapp_san_opts, group="netapp_nvme")
CONF.register_opts(volume_driver.volume_opts, group="netapp_nvme")

# CONF.set_override("storage_protocol", "NVMe", group="netapp_nvme")
# CONF.set_override("netapp_storage_protocol", "NVMe", group="netapp_nvme")
# Upstream NetApp driver registers this option with choices=["iSCSI", "FC"]
# So "NVMe" will raise a ValueError at boot. Instead, we handle this per-volume below.


class NetappCinderDynamicDriver(NetAppBlockStorageCmodeLibrary):
    """NetApp NVMe driver with dynamic SVM selection from volume types.

    Key difference from standard NetApp drivers:
    - Standard: One SVM per backend, all config in cinder.conf
    - Ours: Multiple SVMs per backend, SVM name from volume type
    """

    def __init__(self, *args, **kwargs):
        # The parent class expects specific driver_name and driver_protocol values.
        # We're inheriting from NetAppBlockStorageCmodeLibrary but using it for NVMe,
        # so we have to be careful with these parameters to avoid conflicts.
        driver_name = kwargs.pop("driver_name", "NetappDynamicCmode")  # noqa: F841
        driver_protocol = kwargs.pop("driver_protocol", "NVMe")  # noqa: F841
        super().__init__(
            *args,
            driver_name=driver_name,
            driver_protocol=driver_protocol,
            **kwargs,
        )
        self.init_capabilities()  # Needed by scheduler via get_volume_stats()
        self.initialized = False  # Required by set_initialized()
        self._stats = {}

    @property
    def supported(self):
        # Used by Cinder to determine whether this driver is active/enabled
        return True

    def get_version(self):
        # Called at Cinder service startup to report backend driver version
        return "NetappCinderDynamicDriver 1.0"

    def init_capabilities(self):
        """Set up driver capabilities for the Cinder scheduler.

        This is standard stuff that every driver needs. The scheduler uses this
        to decide if our backend can handle specific volume requests.
        """
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
        """Mark driver as ready. Cinder calls this after setup is complete."""
        # Called by Cinder VolumeManager at the end of init_host()
        # If not defined, VolumeManager may assume the driver is not ready
        self.initialized = True

        # NetAppBlockStorageCmodeLibrary expects self.ssc_library to be initialized
        # during setup.
        # In the normal NetApp driver, this is done in do_setup().
        # Cinder expects drivers to return a dict with a specific
        # schema from get_volume_stats().
        # This expected schema is:
        # Defined in cinder.volume.driver.BaseVD.get_volume_stats()the base driver class
        # And used later by scheduler and service capability reporting
        # cinder/volume/driver.py
        # get_volume_stats() inside BaseVD
        # _update_volume_stats - contains the keys
        # _update_pools_and_stats

    def _update_volume_stats(self):
        """Refresh our view of available storage pools.

        This is where we differ from standard drivers. Instead of reporting
        pools from one SVM, we need to discover pools from all SVMs that
        have been configured via volume types.
        """
        pools = self._discover_pools()

        self._stats = {
            "volume_backend_name": self.configuration.safe_get("volume_backend_name")
            or "DynamicSVM",
            "vendor_name": "NetApp",
            "driver_version": "1.0",
            "storage_protocol": self.driver_protocol,
            "pools": pools,
        }
        LOG.debug("Updated volume stats with %d pools", len(pools))

    def get_volume_stats(self, refresh=False):
        """Return volume statistics for the scheduler.

        Original NetApp drivers report stats for one SVM. We need to aggregate
        stats from multiple SVMs since we support dynamic selection.

        The tricky part: we don't know which SVMs exist until someone creates
        a volume type with netapp:svm_vserver. So we have to be smart about
        discovery and caching.
        """
        # Called from VolumeManager._report_driver_status()
        # Scheduler and Service report use this to advertise backend capabilities
        # "storage_protocol": "NVMe"Used only for reporting, not actual volume logic
        try:
            if refresh or not self._stats:
                self._update_volume_stats()
            return self._stats
        except Exception as e:
            LOG.error("Failed to get volume stats: %s", e)
            # Don't let stats failures kill the service. Return something basic
            # so the scheduler doesn't think we're dead.
            return {
                "volume_backend_name": self.configuration.safe_get(
                    "volume_backend_name"
                )
                or "DynamicSVM",
                "vendor_name": "NetApp",
                "driver_version": "1.0",
                "storage_protocol": self.driver_protocol,
                "pools": [self._get_fallback_pool()],
            }

    def _build_pool_stats(self, flexvol_name, capacity_info):
        """Convert NetApp capacity info into Cinder pool format.

        This is pretty standard - just converting from NetApp's format
        (bytes with weird key names) to what Cinder expects (GB with
        standard key names).
        """
        total_bytes = capacity_info.get("size-total", 1000 * (1024**3))
        available_bytes = capacity_info.get("size-available", 800 * (1024**3))
        used_bytes = total_bytes - available_bytes

        pool = {
            "pool_name": flexvol_name,
            "total_capacity_gb": int(total_bytes / (1024**3)),
            "free_capacity_gb": int(available_bytes / (1024**3)),
            "provisioned_capacity_gb": int(used_bytes / (1024**3)),
            "allocated_capacity_gb": int(used_bytes / (1024**3)),
            "reserved_percentage": 0,
            "max_over_subscription_ratio": 20.0,
            "thin_provisioning_support": True,
            "thick_provisioning_support": False,
            "multiattach": True,
            "QoS_support": False,
            "compression_support": True,
        }

        LOG.debug(
            "Built pool stats for %s: %dGB total, %dGB free",
            flexvol_name,
            pool["total_capacity_gb"],
            pool["free_capacity_gb"],
        )
        return pool

    def _get_flexvol_capacity_safe(self, flexvol_name):
        """Get FlexVol capacity with proper error handling.

        The NetApp API can be flaky sometimes, especially if someone is
        doing maintenance on the cluster. We don't want capacity queries
        to kill volume stats, so we catch API errors and return defaults.
        """
        try:
            return self._test_client.get_flexvol_capacity(flexvol_name)
        except netapp_api.NaApiError as e:
            LOG.warning("NetApp API error getting capacity for %s: %s", flexvol_name, e)
            # Return reasonable defaults so the pool still shows up
            return {
                "size-total": 1000 * (1024**3),  # 1TB
                "size-available": 800 * (1024**3),  # 800GB
            }
        except Exception as e:
            LOG.error("Unexpected error getting capacity for %s: %s", flexvol_name, e)
            raise

    def _get_dynamic_pool_stats(self):
        """Get real pool stats from NetApp, if we have a connection.

        This is where we actually talk to ONTAP to get FlexVol information.
        The standard NetApp drivers do this during do_setup(), but we can't
        because we don't know which SVM to connect to until volume creation.

        So we're opportunistic: if we have a client from a recent volume
        operation, use it. Otherwise, return fallback stats.
        """
        if not hasattr(self, "_test_client") or not self._test_client:
            LOG.debug("No active NetApp client, returning fallback pool")
            return self._get_fallback_pool()

        pools = []
        try:
            # This is the same API call the standard drivers use
            flexvols = self._test_client.list_flexvols()
            LOG.debug("Discovered %d FlexVols", len(flexvols))

            for flexvol_name in flexvols:
                try:
                    capacity_info = self._get_flexvol_capacity_safe(flexvol_name)
                    pool = self._build_pool_stats(flexvol_name, capacity_info)
                    pools.append(pool)

                except Exception as e:
                    LOG.warning(
                        "Failed to get capacity for FlexVol %s: %s", flexvol_name, e
                    )
                    # Don't let one bad FlexVol kill the whole discovery
                    continue

        except Exception as e:
            LOG.error("Failed to list FlexVols: %s", e)
            return self._get_fallback_pool()

        return pools if pools else [self._get_fallback_pool()]

    def _discover_pools(self):
        """Discover available storage pools from configured SVMs.

        This method attempts to discover pools from any available SVM connections.
        If no connections are available, it returns fallback pool information.
        """
        # Try to get real pool stats if we have an active client
        pools = self._get_dynamic_pool_stats()

        # Ensure we always return a list
        if isinstance(pools, dict):
            return [pools]
        elif isinstance(pools, list):
            return pools
        else:
            return [self._get_fallback_pool()]

    def _get_fallback_pool(self):
        """Return a basic pool when we can't connect to NetApp.

        This keeps the service running even when NetApp is unreachable.
        The scheduler will see we have capacity and might send us requests,
        but those will fail at volume creation time with a proper error.

        Better than having the whole service appear dead.
        """
        # Used internally by get_volume_stats(). The keys listed here are standard
        # and expected by Cinder's scheduler filters.
        # Reference: https://docs.openstack.org/cinder/latest/contributor/drivers.html#reporting-pool-information
        return {
            "pool_name": "dynamic_pool",
            "total_capacity_gb": 1000,
            "free_capacity_gb": 800,
            "reserved_percentage": 0,
            "max_over_subscription_ratio": 20.0,
            "provisioned_capacity_gb": 200,
            "allocated_capacity_gb": 100,
            "thin_provisioning_support": True,
            "thick_provisioning_support": False,
            "multiattach": True,
            "QoS_support": False,
            "compression_support": False,
        }

    def get_filter_function(self):
        # Required for Cinder's scheduler. If not present, Cinder logs an AttributeError
        return self.configuration.safe_get("filter_function") or None

    def get_goodness_function(self):
        # Paired with get_filter_function for scoring
        return self.configuration.safe_get("goodness_function") or None

    def do_setup(self, context):
        """Driver initialization. We keep this minimal.

        Standard NetApp drivers do a lot of work here - connecting to the SVM,
        initializing libraries, etc. We can't do that because we don't know
        which SVM to connect to until someone creates a volume.

        So we just set up the bare minimum to keep Cinder happy.
        """
        # Required by VolumeDriver base class.
        # In our case, all backend config is injected per volume,
        # so we do not need static setup.
        self.ssc_library = ""  # Set to avoid crash in _get_pool_stats()
        LOG.info("NetApp dynamic driver setup completed")

    def check_for_setup_error(self):
        """Validate driver setup. We defer most validation to runtime.

        Standard drivers validate their config here. We can't because our
        "config" is partially in volume types that might not exist yet.

        So we just log that we're doing runtime validation instead.
        """
        LOG.debug("NetApp dynamic driver: runtime validation enabled")

    def update_provider_info(self, *args, **kwargs):
        """Update provider info for existing volumes.

        This is called during service startup to sync our view of volumes
        with what's actually on the storage. The parent class has some
        weird argument handling, so we have to be defensive here.
        """
        # Called during _sync_provider_info() in VolumeManager.
        # If not implemented, Cinder raises a TypeError during service startup.
        # Wrote this logic because it was registered with 3 and was called using 2 args
        try:
            if len(args) == 2:
                volumes, snapshots = args
            elif len(args) >= 3:
                _, volumes, snapshots = args[:3]
            else:
                raise TypeError(
                    "update_provider_info() expects at least volumes and snapshots."
                )
            return {}, {}
        except Exception as e:
            LOG.error("Error in update_provider_info: %s", e)
            return {}, {}

    def set_throttle(self):
        """Set throttle limits. Not applicable for our driver."""
        # Got AttributeError
        pass

        # Required if inheriting from block_cmode.
        # Default uses ZAPI to delete old QoS groups.
        # Since we're using REST and dynamic config, we override this to avoid ZAPI use.

    def _mark_qos_policy_group_for_deletion(self, *args, **kwargs):
        LOG.debug("Skipping ZAPI-based QoS deletion in dynamic REST driver.")

    def _init_rest_client(self, hostname, username, password, vserver):
        """Create a REST client for talking to ONTAP.

        This is where the magic happens. Standard NetApp drivers create one
        client during do_setup() and use it for everything. We create clients
        on-demand based on the SVM specified in the volume type.

        The connection parameters (hostname, username, password) come from
        cinder.conf. Only the vserver (SVM name) comes from
        the volume type.
        """
        # Called from create_volume() to create per-SVM REST connection
        # This avoids use of global CONF and uses metadata-driven parameters
        if not all([hostname, username, password, vserver]):
            raise exception.InvalidInput(
                reason="Missing required parameters for NetApp connection"
            )
        try:
            # Same REST client the standard drivers use, just with dynamic params
            client = RestNaServer(
                hostname=hostname,
                username=username,
                password=password,
                vserver=vserver,
                api_trace_pattern="(.*)",
                private_key_file=None,
                certificate_file=None,
                ca_certificate_file=None,
                certificate_host_validation=False,
                transport_type="https",
                ssl_cert_path=None,
                ssl_cert_password=None,
                port=443,
            )
            # Always test the connection before returning the client.
            # Better to fail fast here than during volume operations.
            version = client.get_ontap_version()
            LOG.info("Connected to NetApp ONTAP %s on SVM %s", version, vserver)
            return client

        except netapp_api.NaApiError as e:
            LOG.error("NetApp API error connecting to SVM %s: %s", vserver, e)
            raise exception.VolumeBackendAPIException(data=f"NetApp error: {e}") from e
        except Exception as e:
            LOG.error(
                "Failed to connect to NetApp SVM %s at %s: %s", vserver, hostname, e
            )
            raise exception.VolumeBackendAPIException(
                data=f"Connection failed to {hostname}: {e}"
            ) from e

    def clean_volume_file_locks(self, volume):
        """Clean up file locks for a volume.

        This is a ZAPI thing that doesn't apply to REST. But Cinder calls it
        during cleanup, so we need the method to exist.
        """
        LOG.debug("No-op clean_volume_file_locks in dynamic driver")

    def create_volume(self, volume):
        # Called directly by Cinder during volume create workflow (create_volume.py)
        # This is where we extract runtime metadata (hostname, creds, protocol, etc.)
        # from volume type extra_specs and establish REST client connection.
        specs = volume.volume_type.extra_specs
        hostname = specs.get("netapp:svm_hostname")
        username = specs.get("netapp:svm_username")
        password = specs.get("netapp:svm_password")
        vserver = specs.get("netapp:svm_vserver")
        protocol = specs.get("netapp:svm_protocol", "NVMe")

        if not all([hostname, username, password, vserver]):
            raise exception.VolumeBackendAPIException(data="Missing NetApp metadata")

        client = self._init_rest_client(hostname, username, password, vserver)  # noqa: F841

        if protocol == "iscsi":
            LOG.info("Provisioning via iSCSI")
        elif protocol == "NVMe":
            LOG.info("Provisioning via NVMe")
            # TODO: Inherit these from client_cmode
            # Call create or get NVMe subsystem
            # Add host initiator to subsystem
            # Create namespace backed by FlexVol
            # Map namespace to subsystem
        else:
            LOG.info(" .WIP. ")
