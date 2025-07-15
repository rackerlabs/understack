"""Metadata-based backend config."""

from cinder import exception
from cinder.volume import driver as volume_driver
from cinder.volume.drivers.netapp import options
from cinder.volume.drivers.netapp.dataontap.block_cmode import (
    NetAppBlockStorageCmodeLibrary,
)
from cinder.volume.drivers.netapp.dataontap.client.client_cmode_rest import (
    RestClient as RestNaServer,
)
from oslo_config import cfg
from oslo_log import log as logging

# Dev: from remote_pdb import RemotePdb

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

# Register necessary config options under a unique group name 'dynamic_netapp'
CONF.register_opts(options.netapp_connection_opts, group="dynamic_netapp")
CONF.register_opts(options.netapp_transport_opts, group="dynamic_netapp")
CONF.register_opts(options.netapp_basicauth_opts, group="dynamic_netapp")
CONF.register_opts(options.netapp_provisioning_opts, group="dynamic_netapp")
CONF.register_opts(options.netapp_cluster_opts, group="dynamic_netapp")
CONF.register_opts(options.netapp_san_opts, group="dynamic_netapp")
CONF.register_opts(volume_driver.volume_opts, group="dynamic_netapp")

# CONF.set_override("storage_protocol", "NVMe", group="dynamic_netapp")
# CONF.set_override("netapp_storage_protocol", "NVMe", group="dynamic_netapp")
# Upstream NetApp driver registers this option with choices=["iSCSI", "FC"]
# So "NVMe" will raise a ValueError at boot. Instead, we handle this per-volume below.


class NetappCinderDynamicDriver(NetAppBlockStorageCmodeLibrary):
    """Metadata-based backend config."""

    def __init__(self, *args, **kwargs):
        # NetApp driver requires 'driver_name' and 'driver_protocol'
        # These are mandatory for the superclass constructor
        driver_name = kwargs.pop("driver_name", "NetappDynamicCmode")  # noqa: F841
        driver_protocol = kwargs.pop("driver_protocol", "NVMe")  # noqa: F841
        super().__init__(
            *args,
            driver_name="NetApp_Dynamic",
            driver_protocol="dynamic",
            **kwargs,
        )
        self.init_capabilities()  # Needed by scheduler via get_volume_stats()
        self.initialized = False  # Required by set_initialized()

    @property
    def supported(self):
        # Used by Cinder to determine whether this driver is active/enabled
        return True

    def get_version(self):
        # Called at Cinder service startup to report backend driver version
        return "NetappCinderDynamicDriver 1.0"

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

    def get_volume_stats(self, refresh=False):
        # Called from VolumeManager._report_driver_status()
        # Scheduler and Service report use this to advertise backend capabilities
        # "storage_protocol": "NVMe"Used only for reporting, not actual volume logic
        return {
            "volume_backend_name": "DynamicSVM",
            "vendor_name": "NetApp",
            "driver_version": "1.0",
            "storage_protocol": "NVMe",
            "pools": [self._get_dynamic_pool_stats()],
        }

    def _get_dynamic_pool_stats(self):
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
        # Required by VolumeDriver base class.
        # In our case, all backend config is injected per volume,
        # so we do not need static setup.
        self.ssc_library = ""  # Set to avoid crash in _get_pool_stats()

    def check_for_setup_error(self):
        # Called after do_setup() — used to validate static config.
        # In our case, there's no static setup, so it's a no-op.
        LOG.info(
            "NetApp Dynamic Driver: No setup error check. Validating at volume runtime."
        )

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

        # Required if inheriting from block_cmode.
        # Default uses ZAPI to delete old QoS groups.
        # Since we're using REST and dynamic config, we override this to avoid ZAPI use.

    def _mark_qos_policy_group_for_deletion(self, *args, **kwargs):
        LOG.debug("Skipping ZAPI-based QoS deletion in dynamic REST driver.")

    def _init_rest_client(self, hostname, username, password, vserver):
        # Called from create_volume() to create per-SVM REST connection
        # This avoids use of global CONF and uses metadata-driven parameters
        return RestNaServer(
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
