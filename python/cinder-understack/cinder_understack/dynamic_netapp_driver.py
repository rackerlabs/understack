"""NetApp NVMe driver with dynamic multi-SVM support."""

from cinder import context
from cinder import exception
from cinder import interface
from cinder.objects import volume_type as vol_type_obj
from cinder.volume import driver as volume_driver
from cinder.volume.drivers.netapp import options as na_opts
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
    na_opts.netapp_connection_opts,
    na_opts.netapp_basicauth_opts,
    na_opts.netapp_transport_opts,
    na_opts.netapp_provisioning_opts,
    na_opts.netapp_support_opts,
    na_opts.netapp_san_opts,
    na_opts.netapp_cluster_opts,
]


class NetappDynamicLibrary(NetAppNVMeStorageLibrary):
    """NetApp NVMe storage library with dynamic SVM selection from volume types.

    Key difference from standard NetApp drivers:
    - Standard: One SVM per backend, all config in cinder.conf
    - Ours: Multiple SVMs per backend, SVM name from volume type
    """

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
        """Get pools for a specific SVM.

        Creates SSC and performance libraries for the SVM, then builds
        pool objects from FlexVols with SVM-prefixed names to avoid conflicts.
        """
        pools = []

        try:
            # Create SSC library for this specific SVM  (not global)
            ssc_library = capabilities.CapabilitiesLibrary(
                protocol="nvme",
                vserver_name=svm_name,  # SVM-specific
                zapi_client=client,  # SVM-specific client
                configuration=self.configuration,
            )
            # Get FlexVols for this SVM
            flexvol_names = client.list_flexvols()  # SVM-specific call
            LOG.info(
                "Processing SVM %s: found %d FlexVols %s",
                svm_name,
                len(flexvol_names),
                flexvol_names,
            )

            # Create flexvol mapping with SVM prefix to avoid conflicts
            flexvol_map = {}
            for flexvol_name in flexvol_names:
                # Prefix pool name with SVM to avoid conflicts
                pool_name = f"{svm_name}#{flexvol_name}"
                flexvol_map[flexvol_name] = {"pool_name": pool_name}

            # Update SSC for this SVM
            ssc_library.update_ssc(flexvol_map)
            ssc = ssc_library.get_ssc()

            if not ssc:
                LOG.warning("No SSC data for SVM %s", svm_name)
                return pools

            # Create performance library for this SVM
            try:
                perf_library = perf_cmode.PerformanceCmodeLibrary(
                    client
                )  # SVM-specific
                perf_library.update_performance_cache(ssc)
                aggregates = ssc_library.get_ssc_aggregates()
                aggr_cap = client.get_aggregate_capacities(aggregates)
            except Exception as e:
                LOG.warning("Performance library failed for SVM %s: %s", svm_name, e)
                perf_library = None
                aggr_cap = {}

            # Build pools for this SVM, using same logic as original code
            pool_results = []
            for vol_name, vol_info in ssc.items():
                pool_name = f"{svm_name}#{vol_name}"  # SVM-prefixed pool name

                pool = dict(vol_info)
                pool["pool_name"] = pool_name
                # same capabilities as original copied from netappnvme
                pool["QoS_support"] = False
                pool["multiattach"] = False
                pool["online_extend_support"] = False
                pool["consistencygroup_support"] = False
                pool["consistent_group_snapshot_enabled"] = False
                pool["reserved_percentage"] = 0
                pool["max_over_subscription_ratio"] = 20.0

                # Get real capacity from NetApp - use fallback values if API fails
                try:
                    cap = self._get_flexvol_capacity_with_fallback(client, vol_name)
                    if isinstance(cap, dict):
                        if "size-total" in cap and "size-available" in cap:
                            total_bytes = cap["size-total"]
                            free_bytes = cap["size-available"]
                        elif "size_total" in cap and "size_available" in cap:
                            total_bytes = cap["size_total"]
                            free_bytes = cap["size_available"]
                        else:
                            LOG.warning(
                                "Unexpected capacity format for %s: %s",
                                vol_name,
                                cap,
                            )
                            total_bytes = 1000 * (1024**3)  # 1TB fallback
                            free_bytes = 900 * (1024**3)  # 900GB fallback
                    else:
                        # Fallback values
                        LOG.warning(
                            "Non-dict capacity response for %s: %s", vol_name, cap
                        )
                        total_bytes = 1000 * (1024**3)  # 1TB fallback
                        free_bytes = 900 * (1024**3)  # 900GB fallback

                    pool["total_capacity_gb"] = total_bytes // (1024**3)
                    pool["free_capacity_gb"] = free_bytes // (1024**3)

                    # Ensure non-zero capacity for scheduler
                    if pool["total_capacity_gb"] == 0:
                        pool["total_capacity_gb"] = 1000
                        pool["free_capacity_gb"] = 900

                    pool_results.append(f"{pool_name}({pool['total_capacity_gb']}GB)")

                except Exception as e:
                    LOG.warning(
                        "Capacity error for %s: %s, using fallback values",
                        pool_name,
                        e,
                    )
                    # Use fallback values that will allow scheduling
                    pool["total_capacity_gb"] = 1000
                    pool["free_capacity_gb"] = 900
                    pool_results.append(
                        f"{pool_name}(fallback-{pool['total_capacity_gb']}GB)"
                    )

                # Add performance metrics
                if perf_library:
                    try:
                        pool["utilization"] = (
                            perf_library.get_node_utilization_for_pool(vol_name)
                        )
                    except Exception:
                        pool["utilization"] = 50
                else:
                    pool["utilization"] = 50

                # Add aggregate info
                aggr_name = vol_info.get("netapp_aggregate")
                pool["netapp_aggregate_used_percent"] = aggr_cap.get(aggr_name, {}).get(
                    "percent-used", 0
                )

                # Add dedupe info
                try:
                    pool["netapp_dedupe_used_percent"] = (
                        client.get_flexvol_dedupe_used_percent(vol_name)
                    )
                except Exception:
                    pool["netapp_dedupe_used_percent"] = 0

                pools.append(pool)

            # Single consolidated log for all pools processed
            LOG.info(
                "SVM %s contributed %d pools: %s", svm_name, len(pools), pool_results
            )

        except Exception as e:
            LOG.exception("Failed to process SVM %s: %s", svm_name, e)

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
            )
            LOG.error(msg)
            raise exception.VolumeBackendAPIException(data=msg)

        LOG.info("Using SVM %s at %s (user: %s)", vserver, hostname, username)

        try:
            # The original driver creates a single REST client during
            # do_setup() using static configuration.
            # Our dynamic driver needs to connect to different SVMs based on
            # volume type metadata, so we create the client at volume creation
            # time with parameters extracted from the volume type's extra_specs

            # Initialize REST client for this specific SVM
            self.client = self._init_rest_client(hostname, username, password, vserver)
            # TODO WIP: sets self.client for current operation
            # But pool stats methods expect different client patterns
            # This could cause issues with concurrent operations
            self.vserver = vserver  # Set vserver for compatibility

            # Test the connection
            try:
                ontap_version = self.client.get_ontap_version(cached=False)
                LOG.info("Connected to ONTAP %s on SVM %s", ontap_version, vserver)
            except Exception as e:
                LOG.error("Failed to connect to ONTAP SVM %s: %s", vserver, e)
                raise exception.VolumeBackendAPIException(
                    data=f"Cannot connect to NetApp SVM {vserver}: {e}"
                ) from e
            # The original driver initializes these libraries during do_setup().
            # Since our dynamic driver skips static setup,
            # we initialize them during the first volume creation.
            # These libraries are needed for pool statistics and performance
            # monitoring.

            # Initialize SSC library for this SVM
            if not self.ssc_library:
                try:
                    self.ssc_library = capabilities.CapabilitiesLibrary(
                        protocol="nvme",
                        vserver_name=vserver,
                        zapi_client=self.client,
                        configuration=self.configuration,
                    )
                    LOG.info("SSC library initialized for SVM %s", vserver)
                except Exception as e:
                    LOG.warning("Could not initialize SSC library: %s", e)

            # Initialize performance library for this SVM
            if not self.perf_library:
                try:
                    self.perf_library = perf_cmode.PerformanceCmodeLibrary(self.client)
                    LOG.info("Performance library initialized for SVM %s", vserver)
                except Exception as e:
                    LOG.warning("Could not initialize performance library: %s", e)

            # The core namespace creation logic is identical to the original -
            # we reused the exact same pattern.
            # The only difference is we use flexvol_name (extracted from our
            # custom pool format) instead of pool_name directly.

            # Replicate parent create_volume logic with our FlexVol name
            from oslo_utils import units

            namespace = volume.name
            size = int(volume["size"]) * units.Gi  # Convert GB to bytes
            metadata = {
                "OsType": self.namespace_ostype,
                "Path": f"/vol/{flexvol_name}/{namespace}",
            }

            try:
                self.client.create_namespace(flexvol_name, namespace, size, metadata)
                LOG.info("Created namespace %s in FlexVol %s", namespace, flexvol_name)
            except Exception as e:
                LOG.exception(
                    "Exception creating namespace %(name)s in FlexVol "
                    "%(pool)s: %(error)s",
                    {"name": namespace, "pool": flexvol_name, "error": e},
                )
                msg = (
                    f"Volume {namespace} could not be created in FlexVol "
                    f"{flexvol_name}: {e}"
                )
                raise exception.VolumeBackendAPIException(data=msg) from e

            # Update metadata and add to namespace table
            metadata["Volume"] = flexvol_name
            metadata["Qtree"] = None
            handle = f'{self.vserver}:{metadata["Path"]}'

            # Add to namespace table for tracking
            # The original library maintains a namespace_table to
            # cache namespace information for performance. Since our dynamic
            # driver skips the standard do_setup() where this table would
            # normally be initialized, we had to create it manually during
            # volume creation.
            # This table is important for operations like get_pool(),
            # delete_volume(), and connection management.
            from cinder.volume.drivers.netapp.dataontap.nvme_library import (
                NetAppNamespace,
            )

            namespace_obj = NetAppNamespace(handle, namespace, size, metadata)
            if not hasattr(self, "namespace_table"):
                self.namespace_table = {}
            self.namespace_table[namespace] = namespace_obj

            LOG.info("Volume %s creation completed", volume.name)
            return None  # Parent method returns None

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
