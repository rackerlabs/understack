"""NetApp NVMe driver with dynamic multi-SVM support."""

from cinder import context
from cinder import exception
from cinder import interface
from cinder.objects import volume_type as vol_type_obj
from cinder.volume import driver as volume_driver
from cinder.volume.drivers.netapp import options as na_opts
from cinder.volume.drivers.netapp.dataontap.nvme_library import NetAppNVMeStorageLibrary
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

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
    volume_driver.volume_opts,
]


class NetappDynamicLibrary:
    """NetApp NVMe storage library with dynamic SVM selection from volume types.

    Key difference from standard NetApp drivers:
    - Standard: One SVM per backend, all config in cinder.conf
    - Ours: Multiple SVMs per backend, SVM name from volume type
    - Current : Per SVM delegation to upstream NetAppNVMeStorageLibrary instances.
            hence above I have used object instead of NetAppNVMeStorageLibrary
            this design uses composition/delegation, not inheritance
            Each SVM gets its own properly configured NetAppNVMeStorageLibrary
    """

    VERSION = "1.0.0"
    # Added to each svms pool capabilities

    def __init__(self, driver_name, driver_protocol, **kwargs):
        """Initialize the dynamic library with per-SVM delegation."""
        self.driver_name = driver_name
        self.driver_protocol = driver_protocol
        self.configuration = kwargs.get("configuration")
        self.host = kwargs.get("host", "unknown@unknown")
        self.app_version = kwargs.get("app_version", self.VERSION)

        # Per-SVM upstream library instances
        self.svm_libraries = {}  # svm_name -> NetAppNVMeStorageLibrary

        # Driver capabilities
        self._stats = {}

        self._setup_configuration(**kwargs)

    def _setup_configuration(self, **kwargs):
        """Setup configuration using cinder.volume.configuration module."""

        config_obj = kwargs.get("configuration", None)

        if config_obj:
            # here we can access any cinder-provided config .
            self.configuration = config_obj
            config_group = getattr(config_obj, "config_group", "netapp_nvme")

            # Register NetApp-specific options using configuration.append()
            # Following the exact pattern from upstream NetApp drivers

            try:
                for opt_group in NETAPP_DYNAMIC_OPTS:
                    self.configuration.append_config_values(opt_group)

                LOG.info(
                    "Registered NetApp configuration options for group: %s",
                    config_group,
                )

            except Exception as e:
                LOG.warning("Failed to register configuration options: %s", e)
                # Continue default configuration handling for backward compatibility
        else:
            # Testing/Fallback: Create configuration object with all options
            config_group = "netapp_nvme"
            self.configuration = configuration.Configuration(
                volume_driver.volume_opts, config_group=config_group
            )

            # Register additional NetApp options for testing
            try:
                for opt_group in NETAPP_DYNAMIC_OPTS:
                    if (
                        opt_group != volume_driver.volume_opts
                    ):  # Avoid duplicate registration
                        self.configuration.append_config_values(opt_group)

                LOG.info(
                    "Registered NetApp configuration options for testing group: %s",
                    config_group,
                )

            except Exception as e:
                LOG.warning(
                    "Failed to register configuration options for testing: %s", e
                )

    def _create_svm_configuration(self, svm_name):
        """Create a configuration object for a specific SVM."""
        from cinder.volume import configuration

        LOG.debug("Creating SVM configuration for %s", svm_name)

        # Create a new configuration object for this SVM
        svm_config = configuration.Configuration(
            volume_driver.volume_opts,
            config_group=f"{self.configuration.config_group}_{svm_name}",
        )

        # Register all the NetApp option groups
        try:
            for opt_group in NETAPP_DYNAMIC_OPTS:
                if opt_group != volume_driver.volume_opts:
                    svm_config.append_config_values(opt_group)
        except Exception as e:
            LOG.warning(
                "Failed to register configuration options for SVM %s: %s", svm_name, e
            )

        # Copy critical NetApp settings from base configuration
        # helpful while debugging
        # netapp_attrs = [
        #     "netapp_login",
        #     "netapp_password",
        #     "netapp_server_hostname",
        #     "netapp_transport_type",
        #     "netapp_ssl_cert_check",
        #     "netapp_server_port",
        #     "netapp_private_key_file",
        #     "netapp_certificate_file",
        #     "netapp_pool_name_search_pattern",
        #     "netapp_namespace_ostype",
        #     "netapp_host_type",
        #     "netapp_driver_reports_provisioned_capacity",
        #     "volume_backend_name",
        #     "max_over_subscription_ratio",
        #     "reserved_percentage",
        # ]

        # Dynamically copy ALL configuration attributes from base to SVM config
        for opt_group in NETAPP_DYNAMIC_OPTS:
            for opt in opt_group:
                attr_name = opt.name
                if hasattr(self.configuration, attr_name):
                    try:
                        base_value = getattr(self.configuration, attr_name)
                        if base_value is not None:
                            setattr(svm_config, attr_name, base_value)
                            LOG.debug("Copied %s = %s to SVM config", attr_name, base_value)
                    except Exception as e:
                        LOG.debug("Could not copy attribute %s: %s", attr_name, e)

        # for attr in netapp_attrs:
        #     if hasattr(self.configuration, attr):
        #         try:
        #             base_value = getattr(self.configuration, attr)
        #             if base_value is not None:
        #                 setattr(svm_config, attr, base_value)
        #         except Exception as e:
        #             LOG.debug("Could not copy attribute %s: %s", attr, e)

        # Override the vserver setting for this SVM
        svm_config.netapp_vserver = svm_name
        # the reason for this was , there is use of zapi client which needed vserver to be set .
        # I have commented this for now , but I will circle back here for
        # fixing the error ,but yes for now this is not needed
        # also while debugging I saw self.client.vserver was getting set .
        # svm_config.vserver = svm_name  # Required by REST client

        return svm_config

    def _get_or_create_svm_library(self, svm_name):
        """Get or create an upstream library instance for the specified SVM."""
        if svm_name in self.svm_libraries:
            return self.svm_libraries[svm_name]

        LOG.info("Creating upstream library for SVM: %s", svm_name)

        try:
            # Create SVM-specific configuration
            svm_config = self._create_svm_configuration(svm_name)
            # Create the upstream library
            svm_library = NetAppNVMeStorageLibrary(
                driver_name=f"{self.driver_name}_{svm_name}",
                driver_protocol=self.driver_protocol,
                configuration=svm_config,
                host=self.host,
                app_version=self.app_version,
            )

            self.svm_libraries[svm_name] = svm_library
            LOG.info("Successfully created upstream library for SVM: %s", svm_name)
            return svm_library

        except Exception as e:
            LOG.error("Failed to create upstream library for SVM %s: %s", svm_name, e)
            raise exception.VolumeBackendAPIException(
                data=f"Failed to create library for SVM {svm_name}: {e}"
            ) from e

    def _get_svm_from_volume_type(self, volume_type_specs):
        """Extract SVM name from volume type extra specs."""
        if not volume_type_specs:
            raise exception.VolumeBackendAPIException(
                data="Volume type extra specs are required for SVM selection"
            )

        svm_name = volume_type_specs.get("netapp:svm_vserver")
        if not svm_name:
            raise exception.VolumeBackendAPIException(
                data="Missing required NetApp SVM metadata: netapp:svm_vserver"
            )

        return svm_name

    def _get_svm_library_for_volume(self, volume):
        """Get the appropriate SVM library for a volume."""
        specs = na_utils.get_volume_extra_specs(volume)
        if not specs:
            raise exception.VolumeBackendAPIException(
                data="Volume must have a volume type for SVM selection"
            )
        svm_name = self._get_svm_from_volume_type(specs)
        svm_library = self._get_or_create_svm_library(svm_name)

        return svm_library, svm_name

    def do_setup(self, context):
        """Initialize the driver but defer SVM-specific setup until needed."""
        LOG.info("Dynamic NetApp driver setup - SVM libraries created on demand")
        self._stats = {}

    def check_for_setup_error(self):
        """Validate that we can discover SVMs from volume types."""
        try:
            svm_names = self._discover_svms_from_volume_types()
            if not svm_names:
                LOG.warning(
                    "No SVMs found in volume type metadata. "
                    "Ensure volume types have 'netapp:svm_vserver' extra spec."
                )
            else:
                LOG.info(
                    "Discovered %d SVMs from volume types: %s",
                    len(svm_names),
                    svm_names,
                )
        except Exception as e:
            LOG.warning("Could not validate SVM discovery: %s", e)

    def _discover_svms_from_volume_types(self):
        """Discover available SVMs from volume type metadata."""
        svm_names = set()
        try:
            ctxt = context.get_admin_context()
            types = vol_type_obj.VolumeTypeList.get_all(ctxt)

            for vt in types:
                specs = vt.extra_specs
                svm_name = specs.get("netapp:svm_vserver")
                if svm_name:
                    svm_names.add(svm_name)

        except Exception as e:
            LOG.warning("Failed to discover SVMs from volume types: %s", e)

        return list(svm_names)

    def _adjust_host_field_for_upstream(self, volume, svm_library):
        """Adjust host field for upstream library compatibility."""
        original_host = volume.get("host")

        if not original_host:
            return original_host

        host_parts = original_host.split("#")

        if len(host_parts) == 3:
            # Format: hostname@backend#svm#pool -> hostname@backend#pool
            base_host = host_parts[0]
            pool_name = host_parts[2]
            volume["host"] = f"{base_host}#{pool_name}"
            LOG.debug(
                "Adjusted host field for upstream: %s -> %s",
                original_host,
                volume["host"],
            )
        elif len(host_parts) == 1:
            # No pool in host field, add one
            svm_stats = svm_library.get_volume_stats(refresh=True)
            svm_pools = svm_stats.get("pools", [])
            if svm_pools:
                pool_name = svm_pools[0].get("pool_name", "vol1")
                if "#" in pool_name:
                    pool_name = pool_name.split("#")[-1]
                volume["host"] = f"{volume['host']}#{pool_name}"
                LOG.debug("Added pool to host field: %s", volume["host"])
        else:
            raise exception.VolumeBackendAPIException(
                data=f"Invalid host field format: '{original_host}'. "
                 f"Expected 'hostname@backend' or 'hostname@backend#svm#pool', "
                 f"but got {len(host_parts)} parts."
        )

        return original_host



    def _ensure_svm_library_setup(self, svm_library, svm_name):
        """Ensure the SVM library is properly set up and connected."""
        if hasattr(svm_library, "_setup_complete") and svm_library._setup_complete:
            return

        try:
            LOG.info("Setting up upstream library for SVM: %s", svm_name)
            svm_library.do_setup(context.get_admin_context())

            # Override vserver settings after setup
            svm_library.vserver = svm_name

            if hasattr(svm_library, "client") and hasattr(
                svm_library.client, "vserver"
            ):
                svm_library.client.vserver = svm_name
                if hasattr(svm_library.client, "connection"):
                    svm_library.client.connection.set_vserver(svm_name)

            if hasattr(svm_library, "ssc_library") and hasattr(
                svm_library.ssc_library, "vserver_name"
            ):
                svm_library.ssc_library.vserver_name = svm_name

            svm_library.check_for_setup_error()
            svm_library._setup_complete = True
            LOG.info("Completed setup for SVM library: %s", svm_name)

        except Exception as e:
            LOG.error("Failed to setup SVM library for %s: %s", svm_name, e)
            raise exception.VolumeBackendAPIException(
                data=f"Failed to setup SVM library for {svm_name}: {e}"
            ) from e

    def get_volume_stats(self, refresh=False):
        """Get volume stats by aggregating from all SVM libraries."""
        if refresh:
            self._update_volume_stats()
        return self._stats

    def _update_volume_stats(self):
        """Update volume statistics with SVM-aware pool filtering."""
        all_pools = self._get_aggregated_svm_pool_stats()

        filter_func = self.get_filter_function()
        goodness_func = self.get_goodness_function()

        self._stats = {
            "volume_backend_name": (
                self.configuration.safe_get("volume_backend_name") or "dynamic_backend"
            ),
            "vendor_name": "NetApp",
            "driver_version": self.VERSION,
            "storage_protocol": self.driver_protocol,
            "pools": all_pools,
        }

        if filter_func:
            self._stats["filter_function"] = filter_func
        if goodness_func:
            self._stats["goodness_function"] = goodness_func

        pool_summary = [
            f"{p.get('pool_name', 'unknown')}({p.get('total_capacity_gb', 0)}GB)"
            for p in all_pools
        ]
        LOG.info("Updated volume stats: %d pools - %s", len(all_pools), pool_summary)

    def _get_aggregated_svm_pool_stats(self):
        """Aggregate pool stats from all SVM libraries using upstream delegation."""
        all_pools = []
        svm_names = self._discover_svms_from_volume_types()

        if not svm_names:
            LOG.warning(
                "No SVMs discovered from volume types. "
                "Ensure volume types have 'netapp:svm_vserver' extra spec."
            )
            return []

        for svm_name in svm_names:
            try:
                svm_library = self._get_or_create_svm_library(svm_name)
                self._ensure_svm_library_setup(svm_library, svm_name)

                # Get pool stats from upstream library
                svm_stats = svm_library.get_volume_stats(refresh=False)
                svm_pools = svm_stats.get("pools", [])

                if not svm_pools:
                    svm_library._update_volume_stats()
                    svm_stats = svm_library.get_volume_stats(refresh=False)
                    svm_pools = svm_stats.get("pools", [])

                if not isinstance(svm_pools, list):
                    svm_pools = [svm_pools] if svm_pools else []

                # Add SVM prefix and metadata to pools
                for pool in svm_pools:
                    if isinstance(pool, dict):
                        original_name = pool.get("pool_name") or "unknown"

                        # Check if pool name already has SVMprefix
                        # to prevent duplication
                        if not original_name.startswith(f"{svm_name}#"):
                            pool["pool_name"] = f"{svm_name}#{original_name}"
                        else:
                            pool["pool_name"] = original_name

                        if "capabilities" not in pool:
                            pool["capabilities"] = {}

                        # Set SVM-specific capabilities for scheduler filtering
                        pool["capabilities"]["netapp:svm_vserver"] = svm_name
                        pool["capabilities"]["svm_name"] = svm_name

                        all_pools.append(pool)

            except Exception as e:
                LOG.warning("Failed to get stats from SVM %s: %s", svm_name, e)

        return all_pools

    def get_filter_function(self):
        """Return the filter function for Cinder's scheduler filtering."""
        # Check if there's a custom filter function in configuration
        base_filter = self.configuration.safe_get("filter_function")
        if base_filter:
            return base_filter

        # For multi-SVM environments, ensure SVM matching
        svm_names = self._discover_svms_from_volume_types()
        if len(svm_names) <= 1:
            return None

        # Multiple SVMs - ensure proper SVM matching
        # This string is passed to Cinder's scheduler via
        # the filter_function field in volume stats
        # During volume scheduling,
        # Cinder's DriverFilter evaluates this expression for each pool
        # pool['capabilities']['netapp:svm_vserver']
        # == volume_type['extra_specs']['netapp:svm_vserver']
        return (
            "capabilities.get('netapp:svm_vserver') == "
            "extra_specs.get('netapp:svm_vserver')"
        )

    def get_goodness_function(self):
        """Return the goodness function for Cinder's scheduler scoring."""
        return self.configuration.safe_get("goodness_function")

    def update_provider_info(self, *args, **kwargs):
        """Update provider info for existing volumes."""
        # This is typically a no-op for most drivers
        return {}, {}

    def get_pool(self, volume):
        """Get pool name for volume prevents host field corruption."""
        current_host = volume.get("host", "")

        # If pool already in host field, return None to prevent DB update
        if "#" in current_host:
            LOG.debug(
                "Pool already present in host field for volume %s: %s",
                volume.get("id", "unknown"),
                current_host,
            )
            return None

        # No pool in host field, get it from upstream library
        try:
            svm_library, svm_name = self._get_svm_library_for_volume(volume)
            self._ensure_svm_library_setup(svm_library, svm_name)
            pool_name = svm_library.get_pool(volume)

            if not pool_name:
                return None

            # Add SVM prefix to the pool name
            if not pool_name.startswith(f"{svm_name}#"):
                pool_name = f"{svm_name}#{pool_name}"

            LOG.info(
                "Returning pool name for volume %s: %s",
                volume.get("id", "unknown"),
                pool_name,
            )
            return pool_name

        except Exception as e:
            LOG.warning(
                "Failed to get pool for volume %s: %s", volume.get("id", "unknown"), e
            )
            return None

    @contextmanager
    def _svm_library_context(self, volume):
        """Context manager for operations that don't modify host field."""
        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)
        yield svm_library

    @contextmanager
    def _volume_operation_context(self, volume):
        """Context manager for volume operations setup and cleanup."""
        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        original_host = self._adjust_host_field_for_upstream(volume, svm_library)

        try:
            yield svm_library
        finally:
            if original_host:
                volume["host"] = original_host

    @contextmanager
    def _snapshot_operation_context(self, snapshot):
        """Context manager for snapshot operations setup and cleanup."""
        volume = snapshot.volume
        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)
        yield svm_library

    def create_volume(self, volume):
        """Create a volume by passing to the appropriate SVM library."""
        LOG.info("Creating volume %s", volume.name)

        with self._volume_operation_context(volume) as svm_library:
            return svm_library.create_volume(volume)


    def delete_volume(self, volume):
        """Delete a volume by delegating to the appropriate SVM library."""
        LOG.info("Deleting volume %s", volume.name)

        with self._volume_operation_context(volume) as svm_library:
            return svm_library.delete_volume(volume)

    # Delegate snapshot operations to upstream library
    def create_snapshot(self, snapshot):
        """Create a snapshot."""
        LOG.info("Creating snapshot %s", snapshot.name)

        with self._snapshot_operation_context(snapshot) as svm_library:
            return svm_library.create_snapshot(snapshot)

    def delete_snapshot(self, snapshot):
        """Delete a snapshot."""
        LOG.info("Deleting snapshot %s", snapshot.name)

        with self._snapshot_operation_context(snapshot) as svm_library:
            return svm_library.delete_snapshot(snapshot)

    def create_volume_from_snapshot(self, volume, snapshot):
        """Create a volume from snapshot."""
        LOG.info("Creating volume %s from snapshot %s", volume.name, snapshot.name)

        with self._volume_operation_context(volume) as svm_library:
            return svm_library.create_volume_from_snapshot(volume, snapshot)

    def create_cloned_volume(self, volume, src_vref):
        """Create a cloned volume."""
        LOG.info("Creating cloned volume %s from %s", volume.name, src_vref.name)

        with self._volume_operation_context(volume) as svm_library:
            return svm_library.create_cloned_volume(volume, src_vref)

    def extend_volume(self, volume, new_size):
        """Extend a volume."""
        LOG.info("Extending volume %s to %s GB", volume.name, new_size)

        with self._volume_operation_context(volume) as svm_library:
            return svm_library.extend_volume(volume, new_size)

    def initialize_connection(self, volume, connector):
        """Initialize connection."""
        LOG.info("Initializing connection for volume %s", volume.name)

        with self._svm_library_context(volume) as svm_library:
            return svm_library.initialize_connection(volume, connector)

    def terminate_connection(self, volume, connector, **kwargs):
        """Terminate connection."""
        LOG.info("Terminating connection for volume %s", volume.name)

        with self._svm_library_context(volume) as svm_library:
            return svm_library.terminate_connection(volume, connector,
                                                    **kwargs)

    def create_export(self, context, volume, connector=None):
        """Create export."""
        with self._svm_library_context(volume) as svm_library:
            return svm_library.create_export(context, volume, connector)

    def ensure_export(self, context, volume):
        """Ensure export."""
        with self._svm_library_context(volume) as svm_library:
            return svm_library.ensure_export(context, volume)

    def remove_export(self, context, volume):
        """Remove export."""
        with self._svm_library_context(volume) as svm_library:
            return svm_library.remove_export(context, volume)


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
        self.library = NetappDynamicLibrary(self.DRIVER_NAME, "NVMe", **kwargs)

    def do_setup(self, context):
        """Setup the driver."""
        self.library.do_setup(context)

    def check_for_setup_error(self):
        """Check for setup errors."""
        self.library.check_for_setup_error()

    def create_volume(self, volume):
        """Create a volume."""
        return self.library.create_volume(volume)

    def delete_volume(self, volume):
        """Delete a volume."""
        return self.library.delete_volume(volume)

    def create_snapshot(self, snapshot):
        """Create a snapshot."""
        return self.library.create_snapshot(snapshot)

    def delete_snapshot(self, snapshot):
        """Delete a snapshot."""
        return self.library.delete_snapshot(snapshot)

    def create_volume_from_snapshot(self, volume, snapshot):
        """Create a volume from a snapshot."""
        return self.library.create_volume_from_snapshot(volume, snapshot)

    def create_cloned_volume(self, volume, src_vref):
        """Create a cloned volume."""
        return self.library.create_cloned_volume(volume, src_vref)

    def extend_volume(self, volume, new_size):
        """Extend a volume."""
        return self.library.extend_volume(volume, new_size)

    def initialize_connection(self, volume, connector):
        """Initialize connection to volume."""
        return self.library.initialize_connection(volume, connector)

    def terminate_connection(self, volume, connector, **kwargs):
        """Terminate connection to volume."""
        return self.library.terminate_connection(volume, connector, **kwargs)

    def get_volume_stats(self, refresh=False):
        """Get volume stats."""
        return self.library.get_volume_stats(refresh)

    def update_provider_info(self, volumes, snapshots):
        """Update provider info."""
        return self.library.update_provider_info(volumes, snapshots)

    def create_export(self, context, volume, connector):
        """Create export for volume."""
        return self.library.create_export(context, volume, connector)

    def ensure_export(self, context, volume):
        """Ensure export for volume."""
        return self.library.ensure_export(context, volume)

    def remove_export(self, context, volume):
        """Remove export for volume."""
        return self.library.remove_export(context, volume)

    def get_pool(self, volume):
        """Get pool name for volume."""
        return self.library.get_pool(volume)


# NOTES
# using Schedular driver filter ; need to have this config
# this might fix os-vol-host-attr:host issue .
# [scheduler] scheduler_default_filters = CapabilitiesFilter,DriverFilter
# Issue with os-vol-host-attr:host
# Netapi Error
