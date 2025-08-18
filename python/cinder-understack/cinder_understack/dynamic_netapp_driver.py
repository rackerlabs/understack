"""NetApp NVMe driver with dynamic multi-SVM support."""

from cinder import context
from cinder import exception
from cinder import interface
from cinder.objects import volume_type as vol_type_obj
from cinder.volume import driver as volume_driver
<<<<<<< HEAD
from cinder.volume.drivers.netapp import options as na_opts
from cinder.volume.drivers.netapp.dataontap.client.client_cmode_rest import (
    RestClient as RestNaServer,
)
=======
from cinder.volume.drivers.netapp import options
>>>>>>> 6cee89ec (per svm code refactored)
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
]


class NetappDynamicLibrary:
    """NetApp NVMe storage library with dynamic SVM selection from volume types.

    Key difference from standard NetApp drivers:
    - Standard: One SVM per backend, all config in cinder.conf
    - Ours: Multiple SVMs per backend, SVM name from volume type
    current : Per SVM delegation to upstream NetAppNVMeStorageLibrary instances.
            hence above I have used object insated of NetAppNVMeStorageLibrary
            this design uses composition/delegation, not inheritance
            Each SVM gets its own properly configured NetAppNVMeStorageLibrary
    """

<<<<<<< HEAD
    REQUIRED_CMODE_FLAGS = []

    def __init__(self, *args, **kwargs):
        """Initialize driver without creating SVM connections.

        Parent driver creates static connections during init. We defer
        SVM connections until volume creation when we know which SVM to use.
        """
        super().__init__(*args, **kwargs)
        self.client = None
        self.ssc_library = None
        self.perf_library = None
=======
    VERSION = "1.0.0"
    # Added to each svms pool capabilities

    def __init__(self, driver_name, driver_protocol, **kwargs):
        """Initialize the dynamic library with per-SVM delegation."""
        self.driver_name = driver_name
        self.driver_protocol = driver_protocol
        self.configuration = kwargs.get("configuration")
        self.host = kwargs.get("host", "unknown@unknown")
        self.app_version = kwargs.get("app_version", "1.0.0")

        # Per-SVM upstream library instances
        self.svm_libraries = {}  # svm_name -> NetAppNVMeStorageLibrary

        # Driver capabilities
        self._stats = {}

        self._setup_configuration(**kwargs)

    def _setup_configuration(self, **kwargs):
        """Setup configuration using cinder.volume.configuration module."""
        from cinder.volume import configuration

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
>>>>>>> 6cee89ec (per svm code refactored)

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

<<<<<<< HEAD
    def _get_all_svm_clients_from_volume_types(self):
        """Connect to all SVMs found in volume type metadata."""
        svm_clients = {}
        ctxt = context.get_admin_context()
=======
        # Copy critical NetApp settings from base configuration
        netapp_attrs = [
            "netapp_login",
            "netapp_password",
            "netapp_server_hostname",
            "netapp_transport_type",
            "netapp_ssl_cert_check",
            "netapp_server_port",
            "netapp_private_key_file",
            "netapp_certificate_file",
            "netapp_pool_name_search_pattern",
            "netapp_namespace_ostype",
            "netapp_host_type",
            "netapp_driver_reports_provisioned_capacity",
            "volume_backend_name",
            "max_over_subscription_ratio",
            "reserved_percentage",
        ]

        for attr in netapp_attrs:
            if hasattr(self.configuration, attr):
                try:
                    base_value = getattr(self.configuration, attr)
                    if base_value is not None:
                        setattr(svm_config, attr, base_value)
                except Exception as e:
                    LOG.debug("Could not copy attribute %s: %s", attr, e)

        # Override the vserver setting for this SVM
        svm_config.netapp_vserver = svm_name
        svm_config.vserver = svm_name  # Required by REST client

        return svm_config

    def _get_or_create_svm_library(self, svm_name):
        """Get or create an upstream library instance for the specified SVM."""
        if svm_name in self.svm_libraries:
            return self.svm_libraries[svm_name]

        LOG.info("Creating upstream library for SVM: %s", svm_name)
>>>>>>> 6cee89ec (per svm code refactored)

        try:
            # Create SVM-specific configuration
            svm_config = self._create_svm_configuration(svm_name)

            # Create the upstream library
            parent_backend = self.host.split("@")[1] if "@" in self.host else "unknown"
            svm_host = f"{self.host.split('@')[0]}@{parent_backend}"

            svm_library = NetAppNVMeStorageLibrary(
                driver_name=f"{self.driver_name}_{svm_name}",
                driver_protocol=self.driver_protocol,
                configuration=svm_config,
                host=svm_host,
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
        if not hasattr(volume, "volume_type") or not volume.volume_type:
            raise exception.VolumeBackendAPIException(
                data="Volume must have a volume type for SVM selection"
            )

        specs = volume.volume_type.extra_specs
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

        return original_host

    def create_volume(self, volume):
        """Create a volume by passing to the appropriate SVM library."""
        LOG.info("Creating volume %s", volume.name)

        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        original_host = self._adjust_host_field_for_upstream(volume, svm_library)

        try:
            result = svm_library.create_volume(volume)
        finally:
            if original_host:
                volume["host"] = original_host

        return result

    def delete_volume(self, volume):
        """Delete a volume by delegating to the appropriate SVM library."""
        LOG.info("Deleting volume %s", volume.name)

        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        original_host = self._adjust_host_field_for_upstream(volume, svm_library)

        try:
            result = svm_library.delete_volume(volume)
        finally:
            if original_host:
                volume["host"] = original_host

        return result

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

<<<<<<< HEAD
    def _get_flexvol_capacity_with_fallback(self, client, vol_name):
        """Get FlexVol capacity with custom volume name to junction path mapping."""
        # TODO : find a API endpoint to fetch the junction path with svm and pool
        try:
            # First try the standard method
            return client.get_flexvol_capacity(vol_name)
        except Exception as e:
            LOG.debug("Standard capacity retrieval failed for %s: %s", vol_name, e)

            try:
                # Use the same query pattern as list_flexvols() but with capacity fields
                query = {
                    "type": "rw",
                    "style": "flex*",  # Match both 'flexvol' and 'flexgroup'
                    "is_svm_root": "false",
                    "error_state.is_inconsistent": "false",
                    "state": "online",
                    "fields": "name,space.available,space.size,nas.path",
                }

                # Get all volumes like list_flexvols() does
                volumes_response = client.send_request(
                    "/storage/volumes/", "get", query=query
                )
                records = volumes_response.get("records", [])

                # Filter for the specific volume we want with multiple matching patterns
                target_volume = None
                for volume in records:
                    volume_name = volume.get("name", "")
                    volume_path = volume.get("nas", {}).get("path", "")

                    # Pattern 1: Exact name match [Ideal scenario]
                    # but keeping other patterns just to be safe,
                    # we can delete it in future
                    # I might have to circle back here ,
                    # once I find a API endpoint to fetch
                    # the junction path with svm name and pool name
                    if volume_name == vol_name:
                        target_volume = volume
                        LOG.debug("Found target volume by exact name: %s", vol_name)
                        break

                    # Pattern 2: Path normalization (handle leading slash differences)
                    if volume_path:
                        normalized_vol_path = volume_path.lstrip("/")
                        normalized_target_path = vol_name.lstrip("/")
                        if normalized_vol_path == normalized_target_path:
                            target_volume = volume
                            LOG.debug(
                                "Found target volume by path normalization: %s -> %s",
                                vol_name,
                                volume_path,
                            )
                            break

                    # Pattern 3: sto_lun1 -> lun1 matches /lun1
                    if vol_name and volume_path and "_" in vol_name:
                        name_suffix = vol_name.split("_")[-1]
                        normalized_vol_path = volume_path.lstrip("/")
                        if normalized_vol_path == name_suffix:
                            target_volume = volume
                            LOG.debug(
                                "Found target volume by name suffix mapping: %s -> %s",
                                vol_name,
                                volume_path,
                            )
                            break

                    # Pattern 4: sto_lun1 -> sto-lun1 matches /sto-lun1
                    if vol_name and volume_path:
                        hyphenated_name = vol_name.replace("_", "-")
                        normalized_vol_path = volume_path.lstrip("/")
                        if normalized_vol_path == hyphenated_name:
                            target_volume = volume
                            LOG.debug(
                                "Found target volume by hyphen name mapping: %s -> %s",
                                vol_name,
                                volume_path,
                            )
                            break

                    # Pattern 5: handle cases where path uses hyphens
                    # but name uses underscores
                    if vol_name and volume_path:
                        normalized_vol_path = volume_path.lstrip("/")
                        if normalized_vol_path.replace("-", "_") == vol_name:
                            target_volume = volume
                            LOG.debug(
                                "Found target volume by separator conversion: %s -> %s",
                                vol_name,
                                volume_path,
                            )
                            break

                if not target_volume:
                    volume_names = [vol.get("name", "unknown") for vol in records]
                    volume_paths = [
                        vol.get("nas", {}).get("path", "no-path") for vol in records
                    ]
                    raise Exception(
                        f"Could not find volume {vol_name}. "
                        f"Available volumes: {volume_names}. "
                        f"Available paths: {volume_paths}."
                    )

                # Extract capacity information
                space_info = target_volume.get("space", {})
                total_size = space_info.get("size", 0)
                available_size = space_info.get("available", 0)

                return {
                    "size-total": float(total_size),
                    "size-available": float(available_size),
                }

            except Exception as custom_e:
                LOG.warning(
                    "Custom capacity retrieval also failed for %s: %s",
                    vol_name,
                    custom_e,
                )
                # Return None to trigger fallback values in the calling code
                raise custom_e

    def _init_rest_client(self, hostname, username, password, vserver):
        """Create a NetApp REST client for the specified SVM.

        This creates a connection to a specific Storage Virtual Machine using
        the cluster management credentials. The key difference from the parent
        driver is that we can create multiple clients for different SVMs
        dynamically, rather than being locked to one SVM at startup.

        Args:
            hostname: NetApp cluster management IP/hostname
            username: Cluster admin username
            password: Cluster admin password
            vserver: Target SVM name

        Returns:
            RestClient: Configured NetApp REST client
        """
        LOG.info(
            "Creating REST client for SVM %s at %s (user: %s)",
            vserver,
            hostname,
            username,
        )

        # Called from create_volume() to create per-SVM REST connection
        # This avoids use of global CONF and uses metadata-driven parameters
        # TODO: Need to circle back here for certs
        # FIXME: SSL certificate validation is currently disabled for simplicity.
        # This should be enabled in production environments.
        client = RestNaServer(
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
            certificate_host_validation=False,
        )
        return client

    def clean_volume_file_locks(self, volume):
        """No-op file lock cleanup for REST-based operations.

        Legacy NetApp drivers used file-based locking mechanisms that required
        cleanup after volume operations. Our REST-based approach doesn't use
        file locks, so this is a no-op.

        However, Cinder's cleanup routines still call this method, so we need
        to provide an implementation to prevent AttributeError exceptions.
        """
        # Got this when volume was created and mocked the NetApp connection.
        # When creation failed,
        # it started its cleanup process and errored out for this method.
        # In our case, REST-based NetApp doesn't need this,
        # but must be present to avoid errors.
        LOG.debug("No-op clean_volume_file_locks in dynamic driver")

    def create_volume(self, volume):
        """Create a volume with dynamic SVM selection based on volume type metadata.

        This method completely overrides the parent's create_volume method to handle
        our dynamic pool naming convention (svm_name#flexvol_name).
        """
        LOG.info("Creating volume %s on host %s", volume.name, volume.host)
        # TODO: subsystem
        # Parse the pool name from volume host to handle our
        # svm_name#flexvol_name format
        # Our host format: cinder@netapp_nvme#data-svm1#ucloud1
        # Standard extract_host expects only one #, but we use two
        # So we need custom parsing for our svm_name#flexvol_name format
        if "#" not in volume.host:
            msg = "No pool information found in volume host field."
            LOG.error(msg)
            raise exception.InvalidHost(reason=msg)

        # Split on # and get everything after the backend name
        # The original driver expects a simple pool name (FlexVol name).
        # But our dynamic driver needs to support multiple SVMs,
        # so we created a custom format svm_name#flexvol_name to encode
        # both the SVM and FlexVol information in the pool name.
        # This allows the scheduler to differentiate between FlexVols
        # with the same name on different SVMs.
        host_parts = volume.host.split("#")
        if len(host_parts) < 3:
            # Fallback to standard extraction for single # format
            from cinder.volume import volume_utils

            pool_name = volume_utils.extract_host(volume.host, level="pool")
        else:
            # Our custom format: backend#svm_name#flexvol_name
            # Combine svm_name#flexvol_name as the pool name
            pool_name = "#".join(host_parts[1:])

        if pool_name is None:
            msg = "Pool is not available in the volume host field."
            LOG.error(msg)
            raise exception.InvalidHost(reason=msg)

        # Handle our svm_name#flexvol_name format
        if "#" in pool_name:
            svm_name, flexvol_name = pool_name.split("#", 1)
        else:
            # Fallback for pools without SVM prefix
            flexvol_name = pool_name
            svm_name = None

        # Extract SVM metadata from volume type extra_specs
        specs = volume.volume_type.extra_specs
        LOG.info(
            "Parsed pool %s -> SVM: %s, FlexVol: %s, extra_specs: %s",
            pool_name,
            svm_name,
            flexvol_name,
            specs,
        )

        # Extract SVM name from volume type metadata
        vserver = specs.get("netapp:svm_vserver")

        # Everything else from cinder.conf
        hostname = self.configuration.netapp_server_hostname
        username = self.configuration.netapp_login
        password = self.configuration.netapp_password
        # For NVMe driver, protocol is always nvme

        # Validate required metadata
        if not vserver:
            msg = "Missing required NetApp SVM metadata: netapp:svm_vserver"
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)
        # Validate cinder.conf parameters
        if not all([hostname, username, password]):
            missing_conf = []
            if not hostname:
                missing_conf.append("netapp_server_hostname")
            if not username:
                missing_conf.append("netapp_login")
            if not password:
                missing_conf.append("netapp_password")
            msg = (
                f"Missing required NetApp configuration in cinder.conf: "
                f"{missing_conf}"
=======
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
>>>>>>> 6cee89ec (per svm code refactored)
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

    # Delegate snapshot operations to upstream library
    def create_snapshot(self, snapshot):
        """Create a snapshot."""
        LOG.info("Creating snapshot %s", snapshot.name)

        volume = snapshot.volume
        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        return svm_library.create_snapshot(snapshot)

    def delete_snapshot(self, snapshot):
        """Delete a snapshot."""
        LOG.info("Deleting snapshot %s", snapshot.name)

        volume = snapshot.volume
        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        return svm_library.delete_snapshot(snapshot)

    def create_volume_from_snapshot(self, volume, snapshot):
        """Create a volume from snapshot."""
        LOG.info("Creating volume %s from snapshot %s", volume.name, snapshot.name)

        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        return svm_library.create_volume_from_snapshot(volume, snapshot)

    def create_cloned_volume(self, volume, src_vref):
        """Create a cloned volume."""
        LOG.info("Creating cloned volume %s from %s", volume.name, src_vref.name)

        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        return svm_library.create_cloned_volume(volume, src_vref)

    def extend_volume(self, volume, new_size):
        """Extend a volume."""
        LOG.info("Extending volume %s to %s GB", volume.name, new_size)

        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        return svm_library.extend_volume(volume, new_size)

    def initialize_connection(self, volume, connector):
        """Initialize connection."""
        LOG.info("Initializing connection for volume %s", volume.name)

        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        return svm_library.initialize_connection(volume, connector)

    def terminate_connection(self, volume, connector, **kwargs):
        """Terminate connection."""
        LOG.info("Terminating connection for volume %s", volume.name)

        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)

        return svm_library.terminate_connection(volume, connector, **kwargs)

    def create_export(self, context, volume, connector=None):
        """Create export."""
        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)
        return svm_library.create_export(context, volume, connector)

    def ensure_export(self, context, volume):
        """Ensure export."""
        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)
        return svm_library.ensure_export(context, volume)

    def remove_export(self, context, volume):
        """Remove export."""
        svm_library, svm_name = self._get_svm_library_for_volume(volume)
        self._ensure_svm_library_setup(svm_library, svm_name)
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

    @staticmethod
    def get_driver_options():
        """All options this driver supports."""
        return [item for sublist in NETAPP_DYNAMIC_OPTS for item in sublist]

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

    def create_export(self, context, volume, connector):
        """Create export for volume."""
        return self.library.create_export(context, volume, connector)

    def ensure_export(self, context, volume):
        """Ensure export for volume."""
        return self.library.ensure_export(context, volume)

    def remove_export(self, context, volume):
        """Remove export for volume."""
        return self.library.remove_export(context, volume)
<<<<<<< HEAD
=======

    def get_pool(self, volume):
        """Get pool name for volume."""
        return self.library.get_pool(volume)


# NOTES
# using Schedular driver filter ; need to have this config
# this might fix os-vol-host-attr:host issue .
# [scheduler] scheduler_default_filters = CapabilitiesFilter,DriverFilter
# Issue with os-vol-host-attr:host
# Netapi Error
>>>>>>> 6cee89ec (per svm code refactored)
