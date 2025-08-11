
"""NetApp NVMe driver with dynamic multi-SVM support."""

from cinder import context
from cinder import exception
from cinder import interface
from cinder.objects import volume_type as vol_type_obj
from cinder.volume import driver as volume_driver
from cinder.volume.drivers.netapp import options
from cinder.volume.drivers.netapp.dataontap.client.client_cmode_rest import (
    RestClient as RestNaServer,
)
from cinder.volume.drivers.netapp.dataontap.nvme_library import NetAppNVMeStorageLibrary
from cinder.volume.drivers.netapp.dataontap.performance import perf_cmode
from cinder.volume.drivers.netapp.dataontap.utils import capabilities
from oslo_config import cfg
from oslo_log import log as logging

LOG = logging.getLogger(__name__)
CONF = cfg.CONF

# Configuration options for dynamic NetApp driver
# Using cinder.volume.configuration approach for better abstraction
NETAPP_DYNAMIC_OPTS = [
    options.netapp_proxy_opts,
    options.netapp_connection_opts,
    options.netapp_transport_opts,
    options.netapp_basicauth_opts,
    options.netapp_provisioning_opts,
    options.netapp_cluster_opts,
    options.netapp_san_opts,
    volume_driver.volume_opts,
]


class NetappDynamicLibrary(NetAppNVMeStorageLibrary):
    """NetApp NVMe storage library with dynamic SVM selection from volume types.

    Key difference from standard NetApp drivers:
    - Standard: One SVM per backend, all config in cinder.conf
    - Ours: Multiple SVMs per backend, SVM name from volume type
    """

    def __init__(self, *args, **kwargs):
        """Initialize driver without creating SVM connections.

        Parent driver creates static connections during init. We defer
        SVM connections until volume creation when we know which SVM to use.
        """
        self.initialized = False
        self.client = None
        driver_name = kwargs.pop("driver_name", "NetAppDynamicNVMe")
        driver_protocol = kwargs.pop("driver_protocol", "nvme")
        self.app_version = kwargs.get("app_version", "1.0.0")

        self._setup_configuration(**kwargs)

        super().__init__(driver_name, driver_protocol, **kwargs)
        self.ssc_library = None
        self.perf_library = None
        # Cache for SVM-specific NetAppNVMeStorageLibrary instances
        self.svm_libraries = {}
        self.init_capabilities()

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

    @property
    def supported(self):
        # Used by Cinder to determine whether this driver is active/enabled
        return True

    def get_version(self):
        # Called at Cinder service startup to report backend driver version
        return "NetappCinderDynamicDriver 1.0"

    def do_setup(self, context):
        """Skip static NetApp connections, defer to volume creation time."""
        LOG.info("Skipping static setup, will connect to SVMs dynamically")
        self.namespace_ostype = self.DEFAULT_NAMESPACE_OS
        self.host_type = self.DEFAULT_HOST_TYPE
        self._stats = {}
        self.ssc_library = None
        self.perf_library = None

    def check_for_setup_error(self):
        """Skip static validation since we connect to SVMs dynamically."""
        pass

    def init_capabilities(self):
        """Set driver capabilities for Cinder scheduler."""
        max_over_subscription_ratio = self.configuration.max_over_subscription_ratio
        self._capabilities = {
            "thin_provisioning_support": True,
            "thick_provisioning_support": True,
            "multiattach": True,
            "snapshot_support": True,
            "max_over_subscription_ratio": max_over_subscription_ratio,
        }
        self.capabilities = self._capabilities

    def set_initialized(self):
        """Mark driver as ready for volume operations."""
        self.initialized = True

    def _get_all_svm_clients_from_volume_types(self):
        """Connect to all SVMs found in volume type metadata."""
        svm_clients = {}
        ctxt = context.get_admin_context()

        try:
            types = vol_type_obj.VolumeTypeList.get_all(ctxt)
            connected_svms = []
            failed_svms = []

            for vt in types:
                specs = vt.extra_specs
                svm_name = specs.get("netapp:svm_vserver")

                if svm_name and svm_name not in svm_clients:
                    try:
                        client = self._init_rest_client(
                            self.configuration.netapp_server_hostname,
                            self.configuration.netapp_login,
                            self.configuration.netapp_password,
                            svm_name,
                        )
                        ontap_version = client.get_ontap_version(cached=False)
                        svm_clients[svm_name] = client
                        connected_svms.append(f"{svm_name}({ontap_version})")
                    except Exception as e:
                        failed_svms.append(f"{svm_name}({e})")

            # Single consolidated log message
            if connected_svms or failed_svms:
                LOG.info(
                    "SVM connections - Connected: %s, Failed: %s",
                    connected_svms or "none",
                    failed_svms or "none",
                )

        except Exception as e:
            LOG.exception("Failed to scan volume types: %s", e)

        return svm_clients

    def upstream_lib_instances(self, svm_name, client):
        """
        """
        print(f"DEBUG: upstream_lib_instances called with svm_name={svm_name}")

        if svm_name not in self.svm_libraries:
            print(f"Creating new library for SVM: {svm_name}")  # temp debug

            try:
                # Create a configuration object for this SVM
                from cinder.volume import configuration


                svm_config = configuration.Configuration(
                    volume_driver.volume_opts,
                    config_group=f"netapp_nvme_{svm_name}"
                )

                # Copy all attributes
                debug_copied_attrs = 0
                failed_attrs = []
                for attr_name in dir(self.configuration):
                    if not attr_name.startswith('_') and hasattr(svm_config, attr_name):
                        try:
                            setattr(svm_config, attr_name, getattr(self.configuration, attr_name))
                            debug_copied_attrs += 1
                        except (AttributeError, TypeError) as e:

                            failed_attrs.append(attr_name)
                            pass

                # print(f"DEBUG: copied {debug_copied_attrs} attrs, failed: {failed_attrs}")

                svm_config.netapp_vserver = svm_name


                for opt_group in NETAPP_DYNAMIC_OPTS:
                    try:
                        svm_config.append_config_values(opt_group)
                    except Exception as reg_error:
                        # Options might already be registered, ignore
                        # print(f"Config registration failed: {reg_error}")
                        pass

                # Create the upstream library instance
                # NOTE: upstream expects specific host format, don't change this
                backend_host = f"cinder@netapp_nvme_{svm_name}"

                # print(f"Creating library with backend_host: {backend_host}")

                svm_library = NetAppNVMeStorageLibrary(
                    driver_name=f"{self.driver_name}_{svm_name}",
                    driver_protocol=self.driver_protocol,
                    configuration=svm_config,
                    host=backend_host,
                    app_version=self.app_version
                )

                # Set client directly to skip do_setup()
                svm_library.client = client
                svm_library.rest_client = client
                svm_library.vserver = svm_name
                svm_library.namespace_ostype = self.namespace_ostype or self.DEFAULT_NAMESPACE_OS
                svm_library.host_type = self.host_type or self.DEFAULT_HOST_TYPE

                # Initialize SSC library - HACK: using zapi_client param for REST client
                # because upstream code expects it, even though we're using REST
                svm_library.ssc_library = capabilities.CapabilitiesLibrary(
                    protocol=self.driver_protocol,
                    vserver_name=svm_name,
                    zapi_client=client,  # This is actually REST client but upstream doesn't care
                    configuration=svm_config,
                )

                # This used to fail randomly, added try/catch
                perm_check_failed = False
                try:
                    svm_library.ssc_library.check_api_permissions()
                    svm_library.using_cluster_credentials = (
                        svm_library.ssc_library.cluster_user_supported()
                    )
                except Exception as perm_error:
                    print(f"Permission check failed: {perm_error}")
                    # Continue anyway, might still work
                    svm_library.using_cluster_credentials = True
                    perm_check_failed = True

                svm_library.perf_library = perf_cmode.PerformanceCmodeLibrary(client)

                # Set other attributes - TODO: get these from config instead of hardcoding
                svm_library.max_over_subscription_ratio = (
                    self.max_over_subscription_ratio if hasattr(self, 'max_over_subscription_ratio')
                    else 20.0  # Default from NetApp docs
                )
                svm_library.reserved_percentage = (
                    self.reserved_percentage if hasattr(self, 'reserved_percentage')
                    else 0
                )

                # Ensure namespace table exists - this was missing and caused AttributeError
                if not hasattr(svm_library, 'namespace_table'):
                    svm_library.namespace_table = {}
                    # print("Created empty namespace_table")  # debug

                # Backend name for Cinder scheduler
                svm_library.backend_name = f"netapp_nvme_{svm_name}"

                # Import looping calls - this was causing AttributeError before
                from cinder.volume.drivers.netapp.dataontap.utils import loopingcalls
                svm_library.loopingcalls = loopingcalls.LoopingCalls()

                # Cache it
                self.svm_libraries[svm_name] = svm_library

                LOG.info("Created NetAppNVMeStorageLibrary instance for SVM %s", svm_name)
                print(f"SUCCESS: Library created for {svm_name}" +
                      f" (perm_check_failed={perm_check_failed})")  # temp debug

            except Exception as e:
                print(f"FAILED to create library for {svm_name}: {e}")  # debug
                LOG.warning("Failed to create library instance for SVM %s: %s", svm_name, e)
                # TODO: maybe we should retry once?
                # import time
                # time.sleep(0.5)
                # return self.upstream_lib_instances(svm_name, client)
                return None
        else:
            # print(f"Using cached library for SVM: {svm_name}")  # debug
            pass

        return self.svm_libraries.get(svm_name)

    def get_volume_stats(self, refresh=False):
        self._update_volume_stats()
        return self._stats

    def _update_volume_stats(self):
        """Update volume statistics by aggregating pools from all SVMs."""
        pools = self._get_ssc_pool_stats()

        if not pools:
            LOG.warning("No pools found from any SVM, using fallback")
            pools = [self._get_fallback_pool()]

        self._stats = {
            "volume_backend_name": (
                self.configuration.safe_get("volume_backend_name") or "dynamic_backend"
            ),
            "vendor_name": "NetApp",
            "driver_version": self.VERSION,
            "storage_protocol": self.driver_protocol,
            "pools": pools,
        }

        # Single consolidated log for pool summary
        pool_summary = [
            f"{p.get('pool_name', 'unknown')}({p.get('total_capacity_gb', 0)}GB)"
            for p in pools
        ]
        LOG.info("Updated volume stats: %d pools - %s", len(pools), pool_summary)

    def _get_aggregated_svm_pool_stats(self):
        """Aggregate pool statistics from all available SVMs.

        Connects to each SVM found in volume types and collects their
        FlexVol pools, creating a unified pool list with SVM-prefixed names.
        """
        all_pools = []
        svm_clients = self._get_all_svm_clients_from_volume_types()

        if not svm_clients:
            LOG.warning("No SVM clients available")
            return []

        svm_results = []
        for svm_name, client in svm_clients.items():
            try:
                svm_pools = self._get_svm_specific_pools(svm_name, client)
                all_pools.extend(svm_pools)
                svm_results.append(f"{svm_name}({len(svm_pools)})")
            except Exception as e:
                LOG.warning("Failed to get pools from SVM %s: %s", svm_name, e)
                svm_results.append(f"{svm_name}(failed)")

        # Single log for all SVM processing results
        LOG.info(
            "Pool aggregation results: %s, total pools: %d",
            svm_results,
            len(all_pools),
        )

        if not all_pools:
            fallback_pool = self._get_fallback_pool()
            all_pools.append(fallback_pool)
            LOG.info("Added fallback pool")

        return all_pools

    def _get_svm_specific_pools(self, svm_name, client):
        """
        """
        pools = []

        try:
            # Get or create the upstream library instance for this SVM
            svm_library = self.upstream_lib_instances(svm_name, client)
            if not svm_library:
                LOG.warning("Could not create library instance for SVM %s", svm_name)
                return pools

            # Update the SSC (Storage Service Catalog) for this SVM
            # This is equivalent to what the upstream library does in _update_ssc()
            svm_library._update_ssc()

            # Use the upstream library's _get_pool_stats() method
            # This gives us all the pool statistics with proper capacity,
            # performance metrics, dedupe info, etc.
            upstream_pools = svm_library._get_pool_stats()

            # Prefix pool names with SVM name to avoid conflicts between SVMs
            pool_results = []
            for pool in upstream_pools:
                original_pool_name = pool.get('pool_name', 'unknown')
                prefixed_pool_name = f"{svm_name}#{original_pool_name}"
                pool['pool_name'] = prefixed_pool_name
                pools.append(pool)

                capacity = pool.get('total_capacity_gb', 0)
                pool_results.append(f"{prefixed_pool_name}({capacity}GB)")

            # Single consolidated log for all pools processed
            LOG.info(
                "SVM %s contributed %d pools using upstream library: %s",
                svm_name, len(pools), pool_results
            )

        except Exception as e:
            LOG.exception("Failed to process SVM %s using upstream library: %s", svm_name, e)
            # Fallback to ensure we don't break the entire backend
            return []

        return pools

    def _get_ssc_pool_stats(self):
        """Main entry point for pool statistics - uses aggregated approach."""
        return self._get_aggregated_svm_pool_stats()

    def _get_flexvol_to_pool_map(self):
        """Get the flexvols that match the pool name search pattern.

        The map is of the format suitable for seeding the storage service
        catalog: {<flexvol_name> : {'pool_name': <flexvol_name>}}
        """
        pools = {}
        try:
            flexvol_names = self.client.list_flexvols()

            for flexvol_name in flexvol_names:
                # For dynamic driver, we include all flexvols as potential pools
                pools[flexvol_name] = {"pool_name": flexvol_name}

            LOG.info(
                "Found %d FlexVols for pool mapping: %s",
                len(flexvol_names),
                flexvol_names,
            )

        except Exception as e:
            LOG.warning("Could not get FlexVol list: %s", e)

        return pools

    def _get_fallback_pool(self):
        """Create an emergency fallback pool when no SVMs are available.

        If we can't connect to any SVMs (due to network issues, maintenance, etc.),
        we return a pool with zero capacity. This keeps the backend visible to
        Cinder's scheduler but prevents new volume creation until connectivity
        is restored.

        This is better than crashing or returning no pools at all, which would
        make the scheduler think the backend is completely dead.
        """
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
        """Dynamically fetch FlexVols from the NetApp SVM as available pools.

        Legacy method that fetches pools from a single SVM. The main driver
        now uses _get_aggregated_svm_pool_stats() for multi-SVM support.
        """
        # this works but could be cleaner and this is not used anywhere
        # just used by super, deleting this causes issue
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
            # remote_pdb('0.0.0.0', 5555).set_trace()
            flexvols = self.client.get_flexvols()
            LOG.debug("Discovered FlexVols: %s", [v["name"] for v in flexvols])
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
            pool_list.append(
                {
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
                }
            )

        # For now, return first pool (or enhance get_volume_stats to return all)
        return pool_list[0] if pool_list else {}

    def get_filter_function(self):
        return self.configuration.safe_get("filter_function") or None

    def get_goodness_function(self):
        """Return the goodness function for Cinder's scheduler scoring."""
        return self.configuration.safe_get("goodness_function") or None

    def update_provider_info(self, *args, **kwargs):
        """Update provider info for existing volumes.

        This is called during service startup to sync our view of volumes
        with what's actually on the storage. The parent class has some
        weird argument handling, so we have to be defensive here.
        """
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
        """No-op throttle implementation to prevent AttributeError.

        Some parts of Cinder expect this method to exist for rate limiting,
        but our driver doesn't implement throttling. This empty method
        prevents crashes when Cinder tries to call it.
        """
        # Got AttributeError
        pass

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
        LOG.info("Creating volume %s on host %s", volume.name, volume.host)

        # Parse the pool name from volume host to handle our svm_name#flexvol_name format
        if "#" not in volume.host:
            msg = "No pool information found in volume host field."
            LOG.error(msg)
            raise exception.InvalidHost(reason=msg)

        # Extract SVM and FlexVol names from the host field
        host_parts = volume.host.split("#")
        if len(host_parts) < 3:
            # Fallback to standard extraction for single # format
            from cinder.volume import volume_utils
            pool_name = volume_utils.extract_host(volume.host, level="pool")
        else:
            # Our custom format: backend#svm_name#flexvol_name
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
        vserver = specs.get("netapp:svm_vserver")

        # Validate required metadata
        if not vserver:
            msg = "Missing required NetApp SVM metadata: netapp:svm_vserver"
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

        # Validate cinder.conf parameters
        hostname = self.configuration.netapp_server_hostname
        username = self.configuration.netapp_login
        password = self.configuration.netapp_password

        if not all([hostname, username, password]):
            missing_conf = []
            if not hostname:
                missing_conf.append("netapp_server_hostname")
            if not username:
                missing_conf.append("netapp_login")
            if not password:
                missing_conf.append("netapp_password")
            msg = f"Missing required NetApp configuration in cinder.conf: {missing_conf}"
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

        LOG.info("Using SVM %s at %s (user: %s)", vserver, hostname, username)

        try:
            # Create REST client for this specific SVM
            client = self._init_rest_client(hostname, username, password, vserver)

            # Test the connection
            try:
                ontap_version = client.get_ontap_version(cached=False)
                LOG.info("Connected to ONTAP %s on SVM %s", ontap_version, vserver)
            except Exception as e:
                LOG.error("Failed to connect to ONTAP SVM %s: %s", vserver, e)
                raise exception.VolumeBackendAPIException(
                    data=f"Cannot connect to NetApp SVM {vserver}: {e}"
                ) from e

            # Get or create the upstream library instance for this SVM
            svm_library = self.upstream_lib_instances(vserver, client)
            if not svm_library:
                msg = f"Could not create library instance for SVM {vserver}"
                LOG.error(msg)
                raise exception.VolumeBackendAPIException(data=msg)

            # Create a modified volume object with the correct host format for upstream library
            # The upstream library expects host format: backend@driver#pool_name
            # We need to convert our svm_name#flexvol_name to just flexvol_name

            backend_name = volume.host.split('@')[1].split('#')[0]
            modified_host = f"{volume.host.split('@')[0]}@{backend_name}#{flexvol_name}"

            # trying with temp a volume-like object that supports attribute access
            class VolumeProxy:
                def __init__(self, original_volume, modified_host):
                    self._original = original_volume
                    self._modified_host = modified_host

                def __getattr__(self, name):
                    if name == 'host':
                        return self._modified_host
                    return getattr(self._original, name)

                def __getitem__(self, key):
                    if key == 'host':
                        return self._modified_host
                    if hasattr(self._original, key):
                        return getattr(self._original, key)
                    # Fallback for dictionary-style access
                    if hasattr(self._original, '__getitem__'):
                        return self._original[key]
                    raise KeyError(key)

                def get(self, key, default=None):
                    try:
                        return self[key]
                    except (KeyError, AttributeError):
                        return default

            volume_copy = VolumeProxy(volume, modified_host)

            LOG.info(
                "Delegating volume creation to upstream library for SVM %s, "
                "FlexVol %s, modified host: %s",
                vserver, flexvol_name, volume_copy['host']
            )

            # Delegate to the upstream library's create_volume method
            # This should handles all the namespace creation, metadata management, etc.
            # import pdb
            # pdb.set_trace()
            LOG.info("About to call upstream create_volume with volume_copy: %s", volume_copy)
            LOG.info("SVM library attributes: client=%s, vserver=%s, namespace_ostype=%s",
                     hasattr(svm_library, 'client'),
                     getattr(svm_library, 'vserver', 'None'),
                     getattr(svm_library, 'namespace_ostype', 'None'))

            try:
                result = svm_library.create_volume(volume_copy)
                LOG.info("Upstream create_volume returned: %s", result)
            except Exception as upstream_error:
                LOG.exception("Upstream create_volume failed for volume %s: %s", volume.name, upstream_error)
                raise exception.VolumeBackendAPIException(
                    data=f"Upstream create_volume failed for {volume.name}: {upstream_error}"
                ) from upstream_error

            # Update our namespace table with the created namespace
            if hasattr(svm_library, 'namespace_table') and volume.name in svm_library.namespace_table:
                if not hasattr(self, 'namespace_table'):
                    self.namespace_table = {}
                self.namespace_table[volume.name] = svm_library.namespace_table[volume.name]
                LOG.info("Updated namespace table with volume %s", volume.name)
            else:
                LOG.warning("Volume %s not found in SVM library namespace table after creation", volume.name)

            LOG.info("Volume %s creation completed using upstream library, returning: %s", volume.name, result)
            return result

        except exception.VolumeBackendAPIException:
            # Re-raise Cinder exceptions as-is
            raise
        except Exception as e:
            LOG.exception("Unexpected error creating volume %s: %s", volume.name, e)
            raise exception.VolumeBackendAPIException(
                data=f"Failed to create volume {volume.name}: {e}"
            ) from e

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
        """Delete a volume - enabled for cleanup."""
        LOG.info("Driver delete_volume called for %s", volume.name)
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


# NOTES
# Namespace: Manually created because we skip standard do_setup()
# Pool: Custom svm#flexvol format to support multi-SVM
# Client: Runtime creation based on volume type metadata vs static config
# Metadata: volume type extra_specs vs cinder.conf
# Library Initialization: Lazy initialization during volume creation
# Pool Discovery: Multi-SVM aggregation vs single SVM

